//! Welche Controller-Eingänge wir für unsere eigenen Actions brauchen.
//!
//! WICHTIG: Wir schlagen NIE eigene Controller-Profile vor, sondern hängen
//! unsere Bindings nur an Profile an, die das Spiel selbst vorschlägt.
//! Sonst könnte die Runtime "unser" Profil auswählen und das Spiel hätte
//! keine Eingaben mehr.

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Slot {
    Grip,
    Trigger,
    Buttons,
    Pose,
    Haptic,
}

/// (Slot, Pfad-Endung) für eine Hand
type HandPaths = &'static [(Slot, &'static str)];

const TOUCH_LEFT: HandPaths = &[
    (Slot::Grip, "input/squeeze/value"),
    (Slot::Trigger, "input/trigger/value"),
    (Slot::Buttons, "input/x/click"),
    (Slot::Buttons, "input/y/click"),
    (Slot::Buttons, "input/thumbstick/click"),
    (Slot::Pose, "input/grip/pose"),
    (Slot::Haptic, "output/haptic"),
];
const TOUCH_RIGHT: HandPaths = &[
    (Slot::Grip, "input/squeeze/value"),
    (Slot::Trigger, "input/trigger/value"),
    (Slot::Buttons, "input/a/click"),
    (Slot::Buttons, "input/b/click"),
    (Slot::Buttons, "input/thumbstick/click"),
    (Slot::Pose, "input/grip/pose"),
    (Slot::Haptic, "output/haptic"),
];
const INDEX_BOTH: HandPaths = &[
    (Slot::Grip, "input/squeeze/value"),
    (Slot::Trigger, "input/trigger/value"),
    (Slot::Buttons, "input/a/click"),
    (Slot::Buttons, "input/b/click"),
    (Slot::Buttons, "input/thumbstick/click"),
    (Slot::Pose, "input/grip/pose"),
    (Slot::Haptic, "output/haptic"),
];
const VIVE_BOTH: HandPaths = &[
    (Slot::Grip, "input/squeeze/click"),
    (Slot::Trigger, "input/trigger/value"),
    (Slot::Buttons, "input/trackpad/click"),
    (Slot::Pose, "input/grip/pose"),
    (Slot::Haptic, "output/haptic"),
];
const WMR_BOTH: HandPaths = &[
    (Slot::Grip, "input/squeeze/click"),
    (Slot::Trigger, "input/trigger/value"),
    (Slot::Buttons, "input/thumbstick/click"),
    (Slot::Buttons, "input/trackpad/click"),
    (Slot::Pose, "input/grip/pose"),
    (Slot::Haptic, "output/haptic"),
];

/// (Profil, linke Hand, rechte Hand)
pub const PROFILES: &[(&str, HandPaths, HandPaths)] = &[
    ("/interaction_profiles/oculus/touch_controller", TOUCH_LEFT, TOUCH_RIGHT),
    ("/interaction_profiles/meta/touch_pro_controller", TOUCH_LEFT, TOUCH_RIGHT),
    ("/interaction_profiles/meta/touch_plus_controller", TOUCH_LEFT, TOUCH_RIGHT),
    ("/interaction_profiles/bytedance/pico4_controller", TOUCH_LEFT, TOUCH_RIGHT),
    ("/interaction_profiles/bytedance/pico4s_controller", TOUCH_LEFT, TOUCH_RIGHT),
    ("/interaction_profiles/bytedance/pico_neo3_controller", TOUCH_LEFT, TOUCH_RIGHT),
    ("/interaction_profiles/valve/index_controller", INDEX_BOTH, INDEX_BOTH),
    ("/interaction_profiles/htc/vive_controller", VIVE_BOTH, VIVE_BOTH),
    ("/interaction_profiles/microsoft/motion_controller", WMR_BOTH, WMR_BOTH),
];

/// Liefert alle (Slot, Hand 0/1, voller Pfad) für ein Profil.
pub fn for_profile(profile: &str) -> Option<Vec<(Slot, usize, String)>> {
    let (_, left, right) = PROFILES.iter().find(|(p, _, _)| *p == profile)?;
    let mut out = Vec::new();
    for (hand, (prefix, list)) in [("/user/hand/left/", left), ("/user/hand/right/", right)]
        .into_iter()
        .enumerate()
    {
        for (slot, suffix) in list.iter() {
            out.push((*slot, hand, format!("{prefix}{suffix}")));
        }
    }
    Some(out)
}
