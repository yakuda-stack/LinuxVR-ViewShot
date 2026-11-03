"""
core/desktop_shot.py – 🖥 Bereich des Desktops per Tastenkürzel fotografieren (KDE Plasma).

Das Kürzel läuft über das GlobalShortcuts-Portal: Beim ersten Einschalten fragt KDE
nach der Erlaubnis, danach merkt es sich das Kürzel. Wichtig: BindShortcuts muss bei
JEDEM Start aufgerufen werden, sonst bleibt das Kürzel ab Plasma 6.7 inaktiv – einen
Dialog gibt es dabei nur für neue Kürzel.

Spectacle öffnet die Bereichsauswahl wie ein Snipping Tool, auch für den WayVR-Laser. Mit
Doppelklick oder Enter wird der Bereich bestätigt, Esc bricht ab. Das Bild kommt in den
Foto-Ordner unter desktop/. Dieser Ordner gehört zur Galerie, aber nicht zu den Fotos,
die übersetzt werden.

Die Sitzung hängt an der D-Bus-Verbindung: Das Kürzel geht also nur, solange die App
offen ist.
"""

import importlib
import logging
import secrets
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from core import paths
from core.i18n import tr

DBusAddress = HeaderFields = MatchRule = MessageType = message_bus = new_method_call = None
open_dbus_connection = None


def load_jeepney() -> bool:
    """jeepney laden. Darf mehrfach laufen: Es kann installiert werden, während die App offen ist."""
    global DBusAddress, HeaderFields, MatchRule, MessageType, message_bus, new_method_call
    global open_dbus_connection
    if open_dbus_connection is not None:
        return True
    importlib.invalidate_caches()
    try:
        from jeepney import (DBusAddress, HeaderFields, MatchRule, MessageType, message_bus,
                             new_method_call)
        from jeepney.io.blocking import open_dbus_connection
    except ImportError:
        return False
    return True


DEFAULT_TRIGGER = "ALT+y"      # so will es die XDG-Shortcuts-Vorgabe
DEFAULT_TRIGGER_TEXT = "Alt+Y"
SHORTCUT_ID = "desktop-shot"
PACKAGES = ["python-jeepney", "spectacle"]
SESSION_TOKEN = "viewshot_desktop_shot"
SHOT_DIR = "desktop"
SHOT_TIMEOUT_S = 300           # so lange darf man sich mit dem Markieren Zeit lassen

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS_IFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"
REGISTRY_IFACE = "org.freedesktop.host.portal.Registry"
CONFIGURE_VERSION = 2          # ConfigureShortcuts gibt es ab dieser Portal-Version
RECEIVE_TIMEOUT_S = 0.25       # so oft nach „Ausschalten“ / „Ändern“ schauen


def missing_packages() -> list[str]:
    """Pakete, die für die Funktion noch fehlen."""
    packages = []
    if not load_jeepney():
        packages.append("python-jeepney")
    if shutil.which("spectacle") is None:
        packages.append("spectacle")
    return packages


def shot_path(now: datetime | None = None) -> Path:
    name = (now or datetime.now()).strftime("Desktop_%Y-%m-%d_%H-%M-%S.%f")[:-3] + ".png"
    return paths.photo_dir() / SHOT_DIR / name


def take(path: Path) -> bool:
    """Bereich markieren lassen und speichern. False = abgebrochen (keine Datei).
    Fehler → OSError / SubprocessError."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["spectacle", "--background", "--region", "--output", str(path)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=SHOT_TIMEOUT_S)
    return path.is_file()


class PortalError(Exception):
    """Das Portal fehlt oder hat die Anfrage abgelehnt."""


class Cancelled(PortalError):
    """Der Nutzer hat im KDE-Dialog abgelehnt."""


class PortalSession:
    """Eine Sitzung mit dem Portal. Läuft komplett im eigenen Thread (run)."""

    def __init__(self, stop: threading.Event, configure: threading.Event,
                 on_bound, on_activated, on_old_portal):
        self.stop = stop
        self.configure = configure
        self.on_bound = on_bound          # (Kürzel als Text)
        self.on_activated = on_activated  # ()
        self.on_old_portal = on_old_portal  # () – „Ändern“ gibt es hier nicht
        self.conn = None
        self.session = ""
        self.version = 0

    def run(self) -> None:
        if not load_jeepney():
            raise PortalError("jeepney fehlt")
        self.conn = open_dbus_connection(bus="SESSION")
        try:
            self.register_app()
            self.watch(REQUEST_IFACE, "Response")
            self.watch(SHORTCUTS_IFACE, "Activated")
            self.watch(SHORTCUTS_IFACE, "ShortcutsChanged")
            self.version = self.portal_version()
            self.session = self.create_session()
            self.on_bound(self.bind())
            while not self.stop.is_set():
                if self.configure.is_set():
                    self.configure.clear()
                    self.open_configure()
                msg = self.receive()
                if msg is not None:
                    self.dispatch(msg)
        finally:
            self.close()

    def register_app(self) -> None:
        """App-ID nennen, damit KDE das Kürzel unter „LinuxVR-ViewShot“ führt. Muss der erste
        Portal-Aufruf sein. Ältere Portale kennen das nicht – dann geht es auch ohne."""
        address = DBusAddress(PORTAL_PATH, PORTAL_NAME, REGISTRY_IFACE)
        reply = self.conn.send_and_get_reply(
            new_method_call(address, "Register", "sa{sv}", (paths.DESKTOP_ID, {})))
        if reply.header.message_type == MessageType.error:
            logging.info("Portal: Registry nicht verfügbar: %s", reply.body)

    def watch(self, interface: str, member: str) -> None:
        rule = MatchRule(type="signal", interface=interface, member=member)
        self.conn.send_and_get_reply(message_bus.AddMatch(rule))

    def portal_version(self) -> int:
        address = DBusAddress(PORTAL_PATH, PORTAL_NAME, "org.freedesktop.DBus.Properties")
        reply = self.conn.send_and_get_reply(
            new_method_call(address, "Get", "ss", (SHORTCUTS_IFACE, "version")))
        if reply.header.message_type == MessageType.error:
            raise PortalError(str(reply.body))
        return int(reply.body[0][1])

    def create_session(self) -> str:
        _, results = self.request("CreateSession", "a{sv}", lambda opts: (
            dict(opts, session_handle_token=("s", SESSION_TOKEN)),))
        handle = results.get("session_handle", ("s", ""))[1]
        if not handle:
            raise PortalError("keine Sitzung bekommen")
        return handle

    def bind(self) -> str:
        shortcut = (SHORTCUT_ID, {"description": ("s", tr("desktop_shot_desc")),
                                  "preferred_trigger": ("s", DEFAULT_TRIGGER)})
        _, results = self.request("BindShortcuts", "oa(sa{sv})sa{sv}", lambda opts: (
            self.session, [shortcut], "", opts))
        trigger = trigger_of(results.get("shortcuts", ("", []))[1])
        if trigger is None:
            raise Cancelled("Kürzel nicht vergeben")
        return trigger or DEFAULT_TRIGGER_TEXT

    def open_configure(self) -> None:
        if self.version < CONFIGURE_VERSION:
            self.on_old_portal()
            return
        address = DBusAddress(PORTAL_PATH, PORTAL_NAME, SHORTCUTS_IFACE)
        self.conn.send(new_method_call(address, "ConfigureShortcuts", "osa{sv}", (self.session, "", {})))

    def request(self, method: str, signature: str, body) -> tuple[int, dict]:
        """Portal-Aufruf mit Request-Objekt: wartet auf dessen Response-Signal."""
        token = "viewshot_" + secrets.token_hex(8)
        address = DBusAddress(PORTAL_PATH, PORTAL_NAME, SHORTCUTS_IFACE)
        call = new_method_call(address, method, signature, body({"handle_token": ("s", token)}))
        reply = self.conn.send_and_get_reply(call)
        if reply.header.message_type == MessageType.error:
            raise PortalError(f"{method}: {reply.body}")
        path = reply.body[0]
        while not self.stop.is_set():
            msg = self.receive()
            if msg is None:
                continue
            fields = msg.header.fields
            if (msg.header.message_type == MessageType.signal
                    and fields.get(HeaderFields.interface) == REQUEST_IFACE
                    and fields.get(HeaderFields.path) == path):
                code, results = msg.body
                if code != 0:
                    raise Cancelled(f"{method}: Antwort {code}")
                return code, results
            self.dispatch(msg)
        raise Cancelled("ausgeschaltet")

    def receive(self):
        try:
            return self.conn.receive(timeout=RECEIVE_TIMEOUT_S)
        except TimeoutError:
            return None

    def dispatch(self, msg) -> None:
        fields = msg.header.fields
        if (msg.header.message_type != MessageType.signal
                or fields.get(HeaderFields.interface) != SHORTCUTS_IFACE
                or not msg.body or msg.body[0] != self.session):
            return
        member = fields.get(HeaderFields.member)
        if member == "Activated" and msg.body[1] == SHORTCUT_ID:
            self.on_activated()
        elif member == "ShortcutsChanged":
            trigger = trigger_of(msg.body[1])
            if trigger is not None:
                self.on_bound(trigger or DEFAULT_TRIGGER_TEXT)

    def close(self) -> None:
        try:
            if self.session:
                address = DBusAddress(self.session, PORTAL_NAME, SESSION_IFACE)
                self.conn.send(new_method_call(address, "Close"))
        except OSError:
            pass  # Verbindung ist schon weg – die Sitzung endet damit auch
        self.conn.close()


def trigger_of(shortcuts: list) -> str | None:
    """Kürzel als Text aus a(sa{sv}). None = unser Eintrag fehlt."""
    for shortcut_id, info in shortcuts:
        if shortcut_id == SHORTCUT_ID:
            return info.get("trigger_description", ("s", ""))[1]
    return None


class DesktopShot(QObject):
    """Verbindet das Portal mit der App. Überlebt den Neuaufbau beim Sprachwechsel."""

    bound = pyqtSignal(str)   # Kürzel steht (Text fürs Anzeigen)
    failed = pyqtSignal(str)  # Fehlertext
    taken = pyqtSignal(str)   # Screenshot gespeichert (Pfad)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trigger = ""
        self._thread = None
        self._stop = threading.Event()
        self._configure = threading.Event()
        self._selecting = threading.Lock()  # zweiter Tastendruck öffnet keine zweite Auswahl

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.active:
            return
        self._stop = threading.Event()
        self._configure = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop, self._configure), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.trigger = ""

    def configure(self) -> None:
        """KDE-Dialog zum Ändern des Kürzels öffnen."""
        self._configure.set()

    def _set_trigger(self, trigger: str) -> None:
        self.trigger = trigger
        self.bound.emit(trigger)

    def _run(self, stop: threading.Event, configure: threading.Event) -> None:  # Hintergrund
        session = PortalSession(stop, configure, self._set_trigger, self._shoot,
                                lambda: self.failed.emit(tr("desktop_shot_old_portal")))
        try:
            session.run()
        except Cancelled as e:
            logging.info("Desktop-Screenshot: %s", e)
            if not stop.is_set():
                self._ended(tr("desktop_shot_cancelled"))
        except Exception as e:  # noqa: BLE001 – Portal fehlt, kein D-Bus …
            logging.warning("Desktop-Screenshot: %s", e)
            if not stop.is_set():
                self._ended(tr("desktop_shot_no_portal"))

    def _ended(self, message: str) -> None:
        self.trigger = ""
        self._thread = None  # active = False, bevor die Optionen die Meldung bekommen
        self.failed.emit(message)

    def _shoot(self) -> None:
        if self._selecting.acquire(blocking=False):
            threading.Thread(target=self._take, daemon=True).start()

    def _take(self) -> None:  # Hintergrund – Spectacle soll das Portal nicht aufhalten
        path = shot_path()
        try:
            if take(path):
                self.taken.emit(str(path))
        except (OSError, subprocess.SubprocessError) as e:
            logging.warning("Desktop-Screenshot: %s", e)
            self.failed.emit(tr("desktop_shot_failed"))
        finally:
            self._selecting.release()
