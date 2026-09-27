"""
core/uploader.py – Foto zu directupload.eu hochladen.

directupload.eu hat keine offizielle API. Wir machen deshalb genau das,
was die Webseite im Browser macht (siehe CIncludes/script/m_upload5.js):

  1. POST /api/upload_http_resize.php
       file      = Bild als "data:image/png;base64,…"
       filename  = Dateiname
       showtext  = 0
     → Antwort: eine Bild-ID (Text)

  2. POST /upload_a2/            (normales Formular)
       img_id[]    = ID aus Schritt 1
       file_name[] = Dateiname
       img_resize  = 0,  autodel = 0
     → Ergebnis-Seite (HTML) mit Bild-Link und Lösch-Link

Ändert die Seite ihr Formular, muss man hier nachbessern. Die letzte
Antwort wird deshalb bei Fehlern in UPLOAD_DEBUG gespeichert.

Links werden in uploads.json gemerkt, damit ein Foto nicht doppelt
hochgeladen wird.
"""

import base64
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from core.paths import CONFIG_DIR, LOG_FILE

BASE = "https://www.directupload.eu"
UPLOADS_FILE = CONFIG_DIR / "uploads.json"
UPLOAD_DEBUG = LOG_FILE.parent / "upload_debug.html"
MAX_BYTES = 8 * 1024 * 1024  # Limit der Seite: 8 MB pro Bild
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) LinuxVR-ViewShot"

# So sehen die Links auf der Ergebnis-Seite aus (Beispiele vom Nutzer):
#   https://www.directupload.eu/file/d/9420/9ke32u3k_png.htm
#   https://www.directupload.eu/delfile/QUEzZ3dT…/
RE_VIEW = re.compile(r"https?://(?:www\.)?directupload\.eu/file/d/\d+/[A-Za-z0-9_]+\.htm")
RE_DELETE = re.compile(r"https?://(?:www\.)?directupload\.eu/delfile/[A-Za-z0-9=_%+-]+/?")


class UploadError(Exception):
    pass


# ----------------------------------------------------------------------
# gemerkte Uploads
# ----------------------------------------------------------------------
def load_uploads() -> dict:
    try:
        return json.loads(UPLOADS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def saved_links(photo: Path) -> dict | None:
    """{"view": …, "delete": …} falls das Foto schon hochgeladen wurde."""
    return load_uploads().get(photo.name)


def forget(photo: Path) -> None:
    """Upload-Eintrag entfernen (z. B. weil das Bild online gelöscht wurde)."""
    data = load_uploads()
    if data.pop(photo.name, None) is not None:
        UPLOADS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _remember(photo: Path, links: dict) -> None:
    data = load_uploads()
    data[photo.name] = links
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------
# Hochladen
# ----------------------------------------------------------------------
def _multipart(fields: dict) -> tuple[bytes, str]:
    """Baut einen multipart/form-data-Body (wie FormData im Browser)."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n"
                     f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                     f"{value}\r\n")
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def parse_links(html: str) -> dict:
    """Sucht Bild- und Lösch-Link in der Ergebnis-Seite."""
    view = RE_VIEW.search(html)
    delete = RE_DELETE.search(html)
    if not view or not delete:
        raise UploadError("Links nicht gefunden")
    return {"view": view.group(0), "delete": delete.group(0)}


def upload(photo: Path, data: bytes, mime: str = "image/png") -> dict:
    """Lädt `data` (Bildbytes) hoch und gibt {"view", "delete"} zurück.
    Läuft blockierend → in der UI in einem Hintergrund-Thread aufrufen!"""
    if len(data) > MAX_BYTES:
        raise UploadError("Bild größer als 8 MB")

    # Cookies merken wie ein Browser (PHP-Session der Seite)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    headers = {"User-Agent": USER_AGENT, "Referer": BASE + "/"}

    def request(url, body=None, content_type=None):
        h = dict(headers)
        if content_type:
            h["Content-Type"] = content_type
        req = urllib.request.Request(url, data=body, headers=h)
        with opener.open(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")

    request(BASE + "/")  # Startseite holen → Session-Cookie

    # Schritt 1: Bild senden → ID
    data_url = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    body, ctype = _multipart({"file": data_url, "filename": photo.name, "showtext": "0"})
    img_id = request(BASE + "/api/upload_http_resize.php", body, ctype).strip()
    if not img_id or len(img_id) > 200 or "<" in img_id:
        _debug(img_id)
        raise UploadError("Keine Bild-ID erhalten")

    # Schritt 2: Formular abschicken → Ergebnis-Seite mit Links
    form = urllib.parse.urlencode([
        ("img_id[]", img_id),
        ("file_name[]", photo.name),
        ("img_resize", "0"),
        ("autodel", "0"),
    ]).encode("ascii")
    html = request(BASE + "/upload_a2/", form, "application/x-www-form-urlencoded")
    try:
        links = parse_links(html)
    except UploadError:
        _debug(html)
        raise
    _remember(photo, links)
    return links


def _debug(text: str) -> None:
    try:
        UPLOAD_DEBUG.parent.mkdir(parents=True, exist_ok=True)
        UPLOAD_DEBUG.write_text(text, encoding="utf-8")
    except OSError:
        pass


def is_online(view_url: str) -> bool:
    """Ist das hochgeladene Bild noch da?
    Gelöschte Bilder leiten auf https://www.directupload.eu/404/ um (Status 404).
    Netzwerkfehler werden als Exception weitergegeben → dann NICHTS löschen."""
    req = urllib.request.Request(view_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return "/404" not in resp.geturl()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
