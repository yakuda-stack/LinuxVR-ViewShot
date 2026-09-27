//! Gesten-Logik – reines Rust, kein OpenXR. Dadurch per `cargo test` testbar.
//!
//! Ablauf:
//!   Idle ──(beide Grips, kein Trigger/Knopf, Hände auseinander)──► Arming
//!   Arming ──(0,4 s gehalten)──► Active   (kurzes Vibrieren = Rahmen ist da)
//!   Active ──(Auslöser-Trigger)──► Foto! ──► Cooldown
//!   Active ──(Typ-Trigger, nur manuell)──► Typ wechseln ──► Cooldown
//!   Cooldown ──(Trigger losgelassen)──► Active
//!   Grips loslassen ──► Idle   (aus jedem Zustand)
//!
//! Welche Trigger was tun, steht in `Buttons` (aus layer.json):
//! links / rechts / beide. Ist irgendwo "beide" eingestellt, wartet ein
//! einzelner Trigger kurz (COMBO_WINDOW), ob der zweite noch dazukommt.

use crate::config::Combo;
use std::time::{Duration, Instant};

/// So lange darf der zweite Trigger "nachkommen", damit es als "beide" zählt
pub const COMBO_WINDOW: Duration = Duration::from_millis(150);

/// Tastenbelegung für den offenen Rahmen
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Buttons {
    pub shutter: Combo,
    /// Typ wechseln (Bild → Text → QR) – None = automatischer Modus
    pub mode: Option<Combo>,
}

impl Default for Buttons {
    fn default() -> Self {
        Self { shutter: Combo::Right, mode: None }
    }
}

impl Buttons {
    fn uses_both(&self) -> bool {
        self.shutter == Combo::Both || self.mode == Some(Combo::Both)
    }
}

/// Alles, was wir pro Frame von den Controllern lesen.
#[derive(Clone, Copy, Debug, Default)]
pub struct Inputs {
    pub grip: [f32; 2],    // 0 = links, 1 = rechts
    pub trigger: [f32; 2],
    /// A/B/X/Y oder Stick-Klick irgendwo gedrückt
    pub buttons: bool,
    /// Abstand der Hände in Metern (None = unbekannt)
    pub hand_distance: Option<f32>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    Idle,
    Arming(Instant),
    Active,
    /// Trigger gedrückt, noch unklar ob einer oder beide (seit, welche Hände)
    Pressing(Instant, [bool; 2]),
    Cooldown,
}

/// Was der Layer nach einem Update tun soll.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    None,
    FrameActivated,
    TakePhoto,
    /// Typ weiterschalten (nur manueller Modus)
    CycleType,
    FrameClosed,
}

pub struct Config {
    pub grip_on: f32,
    pub grip_off: f32,
    pub trigger_idle: f32,
    pub trigger_fire: f32,
    pub min_hand_distance: f32,
    pub hold_time: Duration,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            grip_on: 0.8,       // Grip gilt als gedrückt
            grip_off: 0.5,      // darunter: losgelassen (Hysterese gegen Flackern)
            trigger_idle: 0.2,  // Trigger gilt als "nicht gedrückt"
            trigger_fire: 0.8,  // Trigger löst aus
            min_hand_distance: 0.15,
            hold_time: Duration::from_millis(400),
        }
    }
}

pub struct Gesture {
    pub cfg: Config,
    pub state: State,
}

impl Gesture {
    pub fn new() -> Self {
        Self { cfg: Config::default(), state: State::Idle }
    }

    /// Welche Aktion gehört zu diesen Triggern? Danach: Cooldown.
    fn resolve(&mut self, hands: [bool; 2], b: &Buttons) -> Event {
        let combo = match hands {
            [true, true] => Combo::Both,
            [true, false] => Combo::Left,
            _ => Combo::Right,
        };
        self.state = State::Cooldown;
        if combo == b.shutter {
            Event::TakePhoto
        } else if Some(combo) == b.mode {
            Event::CycleType
        } else {
            Event::None
        }
    }

    pub fn update(&mut self, i: &Inputs, now: Instant, b: &Buttons) -> Event {
        let c = &self.cfg;
        let grips_held = i.grip[0] >= c.grip_off && i.grip[1] >= c.grip_off;
        let grips_pressed = i.grip[0] >= c.grip_on && i.grip[1] >= c.grip_on;
        let triggers_idle = i.trigger[0] < c.trigger_idle && i.trigger[1] < c.trigger_idle;
        let fired = [i.trigger[0] >= c.trigger_fire, i.trigger[1] >= c.trigger_fire];
        let hands_apart = i.hand_distance.is_none_or(|d| d >= c.min_hand_distance);

        // Grips losgelassen → immer zurück zu Idle
        if !grips_held {
            let was_open = matches!(self.state, State::Active | State::Pressing(..) | State::Cooldown);
            self.state = State::Idle;
            return if was_open { Event::FrameClosed } else { Event::None };
        }

        match self.state {
            State::Idle => {
                if grips_pressed && triggers_idle && !i.buttons && hands_apart {
                    self.state = State::Arming(now);
                }
                Event::None
            }
            State::Arming(since) => {
                // Während der Haltezeit darf nichts anderes gedrückt werden
                if !triggers_idle || i.buttons || !hands_apart {
                    self.state = State::Idle;
                    Event::None
                } else if now.duration_since(since) >= c.hold_time {
                    self.state = State::Active;
                    Event::FrameActivated
                } else {
                    Event::None
                }
            }
            State::Active => {
                if fired == [false, false] {
                    Event::None
                } else if fired == [true, true] || !b.uses_both() {
                    // eindeutig → sofort, ohne Wartezeit
                    self.resolve(fired, b)
                } else {
                    self.state = State::Pressing(now, fired);
                    Event::None
                }
            }
            State::Pressing(since, hands) => {
                let hands = [hands[0] || fired[0], hands[1] || fired[1]];
                if hands == [true, true] || now.duration_since(since) >= COMBO_WINDOW || fired == [false, false] {
                    // beide da / Zeit um / schon wieder losgelassen (kurzes Antippen)
                    self.resolve(hands, b)
                } else {
                    self.state = State::Pressing(since, hands);
                    Event::None
                }
            }
            State::Cooldown => {
                if triggers_idle {
                    self.state = State::Active;
                }
                Event::None
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inp(grip: f32, trig: [f32; 2], buttons: bool) -> Inputs {
        Inputs { grip: [grip, grip], trigger: trig, buttons, hand_distance: Some(0.3) }
    }
    const NO: [f32; 2] = [0.0, 0.0];
    const L: [f32; 2] = [1.0, 0.0];
    const R: [f32; 2] = [0.0, 1.0];
    const BOTH: [f32; 2] = [1.0, 1.0];
    fn ms(t0: Instant, n: u64) -> Instant {
        t0 + Duration::from_millis(n)
    }
    /// Geste bis "Rahmen aktiv" durchspielen
    fn active(b: &Buttons) -> (Gesture, Instant) {
        let mut g = Gesture::new();
        let t0 = Instant::now();
        g.update(&inp(1.0, NO, false), t0, b);
        assert_eq!(g.update(&inp(1.0, NO, false), ms(t0, 450), b), Event::FrameActivated);
        (g, ms(t0, 450))
    }

    #[test]
    fn full_flow_right_trigger() {
        let b = Buttons::default(); // Auslöser rechts, automatisch
        let (mut g, t) = active(&b);
        // linker Trigger tut nichts
        assert_eq!(g.update(&inp(1.0, L, false), ms(t, 10), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, NO, false), ms(t, 20), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, R, false), ms(t, 30), &b), Event::TakePhoto);
        // Trigger gehalten → kein zweites Foto
        assert_eq!(g.update(&inp(1.0, R, false), ms(t, 100), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, NO, false), ms(t, 200), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, R, false), ms(t, 300), &b), Event::TakePhoto);
        assert_eq!(g.update(&inp(0.0, NO, false), ms(t, 400), &b), Event::FrameClosed);
    }

    #[test]
    fn manual_mode_cycles_with_left() {
        let b = Buttons { shutter: Combo::Right, mode: Some(Combo::Left) };
        let (mut g, t) = active(&b);
        assert_eq!(g.update(&inp(1.0, L, false), ms(t, 10), &b), Event::CycleType);
        assert_eq!(g.update(&inp(1.0, NO, false), ms(t, 20), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, R, false), ms(t, 30), &b), Event::TakePhoto);
    }

    #[test]
    fn both_waits_for_second_trigger() {
        let b = Buttons { shutter: Combo::Both, mode: Some(Combo::Left) };
        let (mut g, t) = active(&b);
        // links zuerst, rechts 80 ms später → "beide" = Foto
        assert_eq!(g.update(&inp(1.0, L, false), ms(t, 10), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, BOTH, false), ms(t, 90), &b), Event::TakePhoto);
        assert_eq!(g.update(&inp(1.0, NO, false), ms(t, 200), &b), Event::None);
        // nur links, lange gehalten → Typ wechseln (nach dem Zeitfenster)
        assert_eq!(g.update(&inp(1.0, L, false), ms(t, 300), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, L, false), ms(t, 400), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, L, false), ms(t, 460), &b), Event::CycleType);
        assert_eq!(g.update(&inp(1.0, NO, false), ms(t, 500), &b), Event::None);
        // links nur kurz angetippt → auch Typ wechseln
        assert_eq!(g.update(&inp(1.0, L, false), ms(t, 600), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, NO, false), ms(t, 620), &b), Event::CycleType);
    }

    #[test]
    fn single_trigger_ignored_when_shutter_is_both() {
        let b = Buttons { shutter: Combo::Both, mode: None };
        let (mut g, t) = active(&b);
        assert_eq!(g.update(&inp(1.0, R, false), ms(t, 10), &b), Event::None);
        assert_eq!(g.update(&inp(1.0, R, false), ms(t, 200), &b), Event::None);
        assert_eq!(g.state, State::Cooldown);
    }

    #[test]
    fn trigger_before_frame_does_nothing() {
        let b = Buttons::default();
        let mut g = Gesture::new();
        let t0 = Instant::now();
        // Grip + Trigger gleichzeitig (z. B. normales Greifen im Spiel) → kein Rahmen
        g.update(&inp(1.0, BOTH, false), t0, &b);
        assert_eq!(g.update(&inp(1.0, BOTH, false), t0 + Duration::from_secs(1), &b), Event::None);
        assert_eq!(g.state, State::Idle);
    }

    #[test]
    fn button_cancels_arming() {
        let b = Buttons::default();
        let mut g = Gesture::new();
        let t0 = Instant::now();
        g.update(&inp(1.0, NO, false), t0, &b);
        g.update(&inp(1.0, NO, true), ms(t0, 100), &b);
        assert_eq!(g.state, State::Idle);
    }

    #[test]
    fn hands_too_close() {
        let b = Buttons::default();
        let mut g = Gesture::new();
        let t0 = Instant::now();
        let mut i = inp(1.0, NO, false);
        i.hand_distance = Some(0.05);
        g.update(&i, t0, &b);
        assert_eq!(g.update(&i, t0 + Duration::from_secs(1), &b), Event::None);
    }
}
