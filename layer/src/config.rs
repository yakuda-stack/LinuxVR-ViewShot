//! Einstellungen aus ~/.config/linuxvr-viewshot/layer.json
//!
//! Die Datei schreibt die Python-UI (Optionen → Shot / ViewShot).
//! Der Layer liest sie höchstens alle 0,5 s neu, wenn sie sich geändert
//! hat – Slider in der UI wirken also sofort, ohne das Spiel neu zu starten.
//!
//! {
//!   "frame_inset_cm": 7,          Rand nach innen (Größe des Rahmens)
//!   "eye_mix": 50,                0 = linkes Auge … 100 = rechtes Auge
//!   "excluded_apps": ["wayvr"],   Programme, in denen ViewShot aus ist
//!   "detect_mode": "auto",        "auto" = UI erkennt Text/QR/Bild,
//!                                 "manual" = Typ in VR wählen (Symbol am Rahmen)
//!   "shutter": "right",           Auslöser: "left" / "right" / "both"
//!   "mode_button": "left",        Typ wechseln (nur manual): "left" / "right" / "both"
//!   "icon_position": "bottom_left" Symbol-Position (manual): "bottom_left" / "bottom_right" / "top_left" / "top_right"
//!   "live_interval_s": 3,         🔁 Lens: alle so viele Sekunden neu fotografieren (→ live/live.png)
//!   "overlay": false,             🥽 🔁 Lens: Übersetzung über dem Original (overlay/overlay.png, malt die UI)
//!   "panel": true,                🪟 Übersetzungs-Panel (panel/panel.png, malt die UI)
//!   "panel_anchor": "left",       hängt an: "left" / "right" (Hand), "head", "world"
//!   "panel_edit": false,          Bearbeiten: Grip = verschieben, Ecke + Trigger = Größe
//!   "panel_port": 47931,          Klicks gehen per UDP an 127.0.0.1:<Port> (die UI)
//!   "panel_opacity": 100,         Deckkraft in % (malt die UI ins Panel-Bild)
//!   "panel_button": true,         🔘 Knopf (Handgelenk) klappt das Panel auf/zu
//!   "panel_button_color": "#5b8dc9"  Farbe des Knopfs (passend zum Hand-Overlay, z. B. WayVR)
//!   "panel_open_on_shot": true,   zugeklapptes Panel geht nach einem Foto von selbst auf
//!   "daemon": "all",              Dienst ohne App starten: "off" / "all" (jedes VR-Spiel) / "selected"
//!   "daemon_apps": []             bei "selected": nur diese Spiele (Teilwort, ohne Groß/Klein)
//! }

use serde::Deserialize;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime};

/// Welche Trigger eine Aktion auslösen
#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Combo {
    Left,
    Right,
    Both,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DetectMode {
    Auto,
    Manual,
}

/// Wann soll der Hintergrund-Dienst (viewshot-daemon) laufen?
#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DaemonMode {
    Off,
    All,
    Selected,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IconPosition {
    BottomLeft,
    BottomRight,
    TopLeft,
    TopRight,
}

impl IconPosition {
    pub fn is_left(self) -> bool {
        matches!(self, Self::BottomLeft | Self::TopLeft)
    }
    pub fn is_top(self) -> bool {
        matches!(self, Self::TopLeft | Self::TopRight)
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(default)]
pub struct LayerConfig {
    pub frame_inset_cm: f32,
    pub eye_mix: f32,
    pub excluded_apps: Vec<String>,
    pub detect_mode: DetectMode,
    pub shutter: Combo,
    pub mode_button: Combo,
    pub icon_position: IconPosition,
    pub live_interval_s: f32,
    pub overlay: bool,
    pub panel: bool,
    pub panel_anchor: crate::panel::Anchor,
    pub panel_edit: bool,
    pub panel_port: u16,
    /// Deckkraft des Panels in % – die UI malt sie ins Bild, hier nur der Vollständigkeit halber
    pub panel_opacity: f32,
    /// 🔘 Knopf am Handgelenk: Panel auf-/zuklappen
    pub panel_button: bool,
    /// Farbe des Knopfs „#rrggbb“
    pub panel_button_color: String,
    /// Nach einem Foto geht das zugeklappte Panel von selbst auf
    pub panel_open_on_shot: bool,
    pub daemon: DaemonMode,
    pub daemon_apps: Vec<String>,
}

impl Default for LayerConfig {
    fn default() -> Self {
        Self {
            frame_inset_cm: 7.0,
            eye_mix: 50.0,
            excluded_apps: vec!["wayvr".into()],
            detect_mode: DetectMode::Auto,
            shutter: Combo::Right,
            mode_button: Combo::Left,
            icon_position: IconPosition::BottomLeft,
            live_interval_s: 3.0,
            overlay: false,
            panel: true,
            panel_anchor: crate::panel::Anchor::Left,
            panel_edit: false,
            panel_port: 47931,
            panel_opacity: 100.0,
            panel_button: true,
            panel_button_color: "#5b8dc9".into(),
            panel_open_on_shot: true,
            daemon: DaemonMode::All,
            daemon_apps: vec![],
        }
    }
}

impl LayerConfig {
    /// Rand in Metern. $VIEWSHOT_INSET_CM hat Vorrang (zum Testen).
    pub fn inset_m(&self) -> f32 {
        let cm = std::env::var("VIEWSHOT_INSET_CM")
            .ok()
            .and_then(|v| v.parse::<f32>().ok())
            .unwrap_or(self.frame_inset_cm);
        cm.clamp(0.0, 30.0) / 100.0
    }

    /// Tasten für die Geste. Typ-Wechsel (auto: 🪄 ↔ 🔁 Lens, manuell: 🖼 📝 🔳 🔁) –
    /// nie auf derselben Taste wie der Auslöser (dann gewinnt der Auslöser).
    pub fn buttons(&self) -> crate::gesture::Buttons {
        let mode = (self.mode_button != self.shutter).then_some(self.mode_button);
        crate::gesture::Buttons { shutter: self.shutter, mode }
    }

    pub fn manual(&self) -> bool {
        self.detect_mode == DetectMode::Manual
    }

    /// Abstand zwischen zwei Live-Fotos (1–30 s)
    pub fn live_interval(&self) -> Duration {
        Duration::from_secs_f32(self.live_interval_s.clamp(1.0, 30.0))
    }

    /// 0.0 = linkes Auge, 1.0 = rechtes Auge
    pub fn eye_t(&self) -> f32 {
        (self.eye_mix / 100.0).clamp(0.0, 1.0)
    }

    /// Soll der Hintergrund-Dienst für dieses Spiel laufen? (Namen wie bei is_excluded)
    pub fn daemon_wanted(&self, names: &[&str]) -> bool {
        match self.daemon {
            DaemonMode::Off => false,
            DaemonMode::All => true,
            DaemonMode::Selected => self.daemon_apps.iter().any(|a| {
                let a = a.trim().to_lowercase();
                !a.is_empty() && names.iter().any(|n| n.to_lowercase().contains(&a))
            }),
        }
    }

    /// Ist diese App ausgeschlossen? Vergleich ohne Groß/Klein, Teilwort reicht
    /// ("wayvr" passt auch auf "WayVR-Dashboard").
    pub fn is_excluded(&self, names: &[&str]) -> Option<String> {
        self.excluded_apps.iter().find_map(|ex| {
            let ex = ex.trim().to_lowercase();
            if ex.is_empty() {
                return None;
            }
            names.iter().any(|n| n.to_lowercase().contains(&ex)).then(|| ex.clone())
        })
    }
}

pub fn path() -> Option<PathBuf> {
    let dir = dirs::config_dir().or_else(|| dirs::home_dir().map(|h| h.join(".config")))?;
    Some(dir.join("linuxvr-viewshot").join("layer.json"))
}

struct Cache {
    config: LayerConfig,
    modified: Option<SystemTime>,
    checked: Option<Instant>,
}

static CACHE: Mutex<Option<Cache>> = Mutex::new(None);

/// Aktuelle Einstellungen (liest die Datei neu, wenn sie sich geändert hat).
pub fn get() -> LayerConfig {
    let mut guard = CACHE.lock().unwrap_or_else(|e| e.into_inner());
    let cache = guard.get_or_insert_with(|| Cache { config: LayerConfig::default(), modified: None, checked: None });

    let due = cache.checked.is_none_or(|t| t.elapsed() >= Duration::from_millis(500));
    if due {
        cache.checked = Some(Instant::now());
        if let Some(p) = path() {
            let modified = std::fs::metadata(&p).and_then(|m| m.modified()).ok();
            if modified != cache.modified {
                cache.modified = modified;
                cache.config = match std::fs::read_to_string(&p) {
                    Ok(text) => match serde_json::from_str(&text) {
                        Ok(c) => {
                            crate::log!("Einstellungen geladen: {c:?}");
                            c
                        }
                        Err(e) => {
                            crate::log!("layer.json fehlerhaft ({e}) – Standardwerte");
                            LayerConfig::default()
                        }
                    },
                    Err(_) => LayerConfig::default(), // Datei gibt es (noch) nicht
                };
            }
        }
    }
    cache.config.clone()
}

/// Name des eigenen Prozesses (z. B. "VRChat.exe", "wayvr")
pub fn process_name() -> String {
    std::fs::read_to_string("/proc/self/comm").map(|s| s.trim().to_string()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn daemon_for_selected_games_only() {
        let c: LayerConfig = serde_json::from_str(r#"{"daemon": "selected", "daemon_apps": ["vrchat"]}"#).unwrap();
        assert!(c.daemon_wanted(&["VRChat", "VRChat.exe"]));
        assert!(!c.daemon_wanted(&["Beat Saber"]));
        assert!(LayerConfig::default().daemon_wanted(&["x"]));
        let off: LayerConfig = serde_json::from_str(r#"{"daemon": "off"}"#).unwrap();
        assert!(!off.daemon_wanted(&["VRChat"]));
    }

    #[test]
    fn exclusion_matches_case_insensitive_substring() {
        let c = LayerConfig { excluded_apps: vec!["WayVR".into(), "  ".into()], ..Default::default() };
        assert_eq!(c.is_excluded(&["wayvr-dashboard"]), Some("wayvr".into()));
        assert_eq!(c.is_excluded(&["VRChat", "VRChat.exe"]), None);
    }

    #[test]
    fn partial_json_uses_defaults() {
        let c: LayerConfig = serde_json::from_str(r#"{"eye_mix": 100}"#).unwrap();
        assert_eq!(c.eye_t(), 1.0);
        assert_eq!(c.frame_inset_cm, 7.0);
        assert_eq!(c.excluded_apps, vec!["wayvr".to_string()]);
        assert_eq!(c.detect_mode, DetectMode::Auto);
        assert_eq!(c.icon_position, IconPosition::BottomLeft);
    }

    #[test]
    fn live_interval_is_clamped() {
        let c: LayerConfig = serde_json::from_str(r#"{"live_interval_s": 0.2}"#).unwrap();
        assert_eq!(c.live_interval(), Duration::from_secs(1));
        assert_eq!(LayerConfig::default().live_interval(), Duration::from_secs(3));
    }

    #[test]
    fn icon_position_from_json() {
        let c: LayerConfig = serde_json::from_str(r#"{"icon_position": "top_right"}"#).unwrap();
        assert_eq!(c.icon_position, IconPosition::TopRight);
        assert!(c.icon_position.is_top() && !c.icon_position.is_left());
    }

    #[test]
    fn buttons_from_json() {
        let c: LayerConfig =
            serde_json::from_str(r#"{"detect_mode": "manual", "shutter": "both", "mode_button": "left"}"#).unwrap();
        let b = c.buttons();
        assert_eq!((b.shutter, b.mode), (Combo::Both, Some(Combo::Left)));
        // gleiche Taste → kein Typ-Wechsel
        let c: LayerConfig =
            serde_json::from_str(r#"{"detect_mode": "manual", "shutter": "left", "mode_button": "left"}"#).unwrap();
        assert_eq!(c.buttons().mode, None);
        // auto → Typ-Wechsel auch (🪄 Auto ↔ 🔁 Lens)
        assert_eq!(LayerConfig::default().buttons().mode, Some(Combo::Left));
    }
}
