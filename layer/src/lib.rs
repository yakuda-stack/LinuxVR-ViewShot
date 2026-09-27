//! LinuxVR-ViewShot – OpenXR API-Layer
//!
//! Was dieser Layer macht (Phase 1 – nur Fotos):
//!  1. Er hängt ein eigenes, unsichtbares "Action-Set" an das Spiel an und
//!     liest darüber Grip, Trigger, Knöpfe und Handpositionen.
//!  2. Die Gesten-Logik (gesture.rs) erkennt den Hand-Rahmen.
//!  3. Beim Trigger-Druck kopiert er in xrEndFrame den Bereich zwischen den
//!     Händen aus dem Bild des linken Auges und speichert ihn als PNG.
//!
//! Hinweis zu `unsafe`: Überall, wo wir Zeiger vom Spiel/der Runtime
//! bekommen (C-Schnittstelle), kann Rust nicht prüfen, ob sie gültig sind.
//! Wir verlassen uns dort auf die OpenXR-Spezifikation – das ist der Grund
//! für die vielen `unsafe`-Blöcke. Unsere eigene Logik ist normales Rust.

#![allow(clippy::missing_safety_doc)]

mod bindings;
mod capture;
mod config;
mod dispatch;
mod frame;
mod gesture;
mod icons;
#[macro_use]
mod log;
mod save;

use dispatch::Next;
use openxr_sys as xr;
use openxr_sys::{pfn, Handle};
use std::collections::{HashMap, VecDeque};
use std::ffi::{c_char, CStr};
use std::sync::{LazyLock, Mutex, MutexGuard};
use std::time::Instant;

// ───────────────────────────── Zustand ─────────────────────────────

/// Unsere Actions – werden für JEDE Session neu erstellt (siehe attach_action_sets).
struct Actions {
    set: xr::ActionSet,
    grip: xr::Action,
    trigger: xr::Action,
    buttons: xr::Action,
    pose: xr::Action,
    haptic: xr::Action,
    hands: [xr::Path; 2],
}

impl Actions {
    fn action_for(&self, slot: bindings::Slot) -> xr::Action {
        match slot {
            bindings::Slot::Grip => self.grip,
            bindings::Slot::Trigger => self.trigger,
            bindings::Slot::Buttons => self.buttons,
            bindings::Slot::Pose => self.pose,
            bindings::Slot::Haptic => self.haptic,
        }
    }
}

struct SwapchainInfo {
    format: i64,
    sample_count: u32,
    transfer_ok: bool,
    images: Vec<u64>,
    acquired: VecDeque<u32>,
    last_released: Option<u32>,
}

/// Vulkan-Handles aus xrCreateSession (als Zahlen gespeichert)
#[derive(Clone, Copy)]
struct VkBinding {
    instance: usize,
    physical_device: usize,
    device: usize,
    queue_family: u32,
    queue_index: u32,
}

struct SessionData {
    /// Unsere Actions für diese Session (None = nicht angehängt)
    actions: Option<Actions>,
    spaces: [xr::Space; 2],
    vk_binding: Option<VkBinding>,
    vk: Option<capture::VkCtx>,
    vk_failed: bool,
    swapchains: HashMap<u64, SwapchainInfo>,
    last_time: xr::Time,
    gesture: gesture::Gesture,
    capture_pending: bool,
    /// Frames seit dem Auslösen ohne erfolgreiche Aufnahme (Diagnose)
    pending_frames: u32,
    /// Anzahl xrEndFrame-Aufrufe (Diagnose)
    frames: u64,
    /// Overlay-App (z. B. WayVR) → ViewShot bleibt dort aus
    overlay: bool,
    /// Letztes Ergebnis von xrSyncActions (Diagnose: fokussiert oder nicht)
    last_sync: xr::Result,
    /// Eigene Swapchain für den sichtbaren Rahmen (Ebene 0 = rot, 1 = weiß)
    frame_sc: Option<xr::Swapchain>,
    /// Rahmen-Anzeige hat einmal nicht geklappt → nicht nochmal versuchen
    frame_failed: bool,
    /// Swapchain mit den Typ-Symbolen (Ebene = PhotoType::index), manueller Modus
    icon_sc: Option<xr::Swapchain>,
    icon_failed: bool,
    /// Weißes Aufblitzen nach dem Foto bis zu diesem Zeitpunkt
    flash_until: Option<Instant>,
}

/// Zustand pro OpenXR-Instanz. Ein Programm kann MEHRERE Instanzen
/// gleichzeitig haben (z. B. wineopenxr erstellt Test-Instanzen parallel).
struct Layer {
    hands: [xr::Path; 2],
    /// Profil-Pfad → (Slot, Eingangs-Pfad) aus bindings.rs, schon als XrPath
    profiles: HashMap<xr::Path, Vec<(bindings::Slot, xr::Path)>>,
    /// Die zuletzt vom Spiel vorgeschlagenen Bindings pro Profil
    app_bindings: HashMap<xr::Path, Vec<xr::ActionSuggestedBinding>>,
    /// Zähler für eindeutige Action-Set-Namen
    set_counter: u32,
    sessions: HashMap<u64, SessionData>,
}

#[derive(Default)]
struct Globals {
    /// Instanz-Handle → Zustand
    instances: HashMap<u64, Layer>,
    /// Funktionen der nächsten Schicht (sind für alle Instanzen gleich).
    /// Bleibt erhalten, auch wenn alle Instanzen beendet sind – so können
    /// wir IMMER an die Runtime weiterreichen.
    next: Option<Next>,
}

impl Globals {
    /// Findet die Instanz, zu der eine Session gehört.
    fn layer_of_session(&mut self, session: xr::Session) -> Option<&mut Layer> {
        self.instances.values_mut().find(|l| l.sessions.contains_key(&session.into_raw()))
    }

    fn session_mut(&mut self, session: xr::Session) -> Option<&mut SessionData> {
        self.layer_of_session(session)?.sessions.get_mut(&session.into_raw())
    }

    fn swapchain_mut(&mut self, sc: xr::Swapchain) -> Option<&mut SwapchainInfo> {
        self.instances
            .values_mut()
            .flat_map(|l| l.sessions.values_mut())
            .find_map(|s| s.swapchains.get_mut(&sc.into_raw()))
    }
}

// Ein globaler Zustand, geschützt durch ein Mutex (mehrere Threads möglich).
static STATE: LazyLock<Mutex<Globals>> = LazyLock::new(|| Mutex::new(Globals::default()));

fn state() -> MutexGuard<'static, Globals> {
    // Falls ein Thread mal abgestürzt ist, trotzdem weitermachen
    STATE.lock().unwrap_or_else(|e| e.into_inner())
}

fn next() -> Option<Next> {
    state().next
}

/// Führt unsere Zusatz-Logik aus. Stürzt sie ab (panic), wird das nur
/// geloggt – das Spiel läuft weiter.
fn guard<R>(what: &str, f: impl FnOnce() -> R) -> Option<R> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(r) => Some(r),
        Err(_) => {
            log!("Interner Fehler in {what} – ignoriert");
            None
        }
    }
}

fn ok(r: xr::Result) -> bool {
    r.into_raw() >= 0 // positive Werte sind auch Erfolg (z. B. SESSION_NOT_FOCUSED)
}

/// Kopiert einen Rust-String in ein festes C-Char-Array (z. B. Action-Namen)
fn fill<const N: usize>(dst: &mut [c_char; N], s: &str) {
    for (d, b) in dst.iter_mut().zip(s.bytes().take(N - 1)) {
        *d = b as c_char;
    }
}

// ─────────────────────── Einstieg: Loader-Verhandlung ───────────────────────

/// Diese Funktion ruft der OpenXR-Loader als Erstes auf (Name steht im
/// Manifest). Wir sagen ihm, welche Funktionen wir anbieten.
#[no_mangle]
pub unsafe extern "system" fn xrNegotiateLoaderApiLayerInterface(
    loader_info: *const xr::NegotiateLoaderInfo,
    _layer_name: *const c_char,
    request: *mut xr::NegotiateApiLayerRequest,
) -> xr::Result {
    if loader_info.is_null() || request.is_null() {
        return xr::Result::ERROR_INITIALIZATION_FAILED;
    }
    let info = &*loader_info;
    let req = &mut *request;
    if info.struct_type != xr::NegotiateLoaderInfo::TYPE
        || req.struct_type != xr::NegotiateApiLayerRequest::TYPE
        || info.min_interface_version > 1
        || info.max_interface_version < 1
    {
        return xr::Result::ERROR_INITIALIZATION_FAILED;
    }
    req.layer_interface_version = 1;
    req.layer_api_version = xr::CURRENT_API_VERSION;
    req.get_instance_proc_addr = Some(get_instance_proc_addr);
    req.create_api_layer_instance = Some(create_api_layer_instance);
    log!("Layer geladen (v{})", env!("CARGO_PKG_VERSION"));
    xr::Result::SUCCESS
}

unsafe extern "system" fn create_api_layer_instance(
    info: *const xr::InstanceCreateInfo,
    layer_info: *const xr::ApiLayerCreateInfo,
    instance: *mut xr::Instance,
) -> xr::Result {
    // Den Loader-Zeiger auf die nächste Schicht "weiterschieben"
    let li = &*layer_info;
    let next_info = &*li.next_info;
    let (Some(next_gipa), Some(next_create)) =
        (next_info.next_get_instance_proc_addr, next_info.next_create_api_layer_instance)
    else {
        return xr::Result::ERROR_INITIALIZATION_FAILED;
    };
    let mut new_li = *li;
    new_li.next_info = next_info.next;
    let res = next_create(info, &new_li, instance);
    if !ok(res) {
        return res;
    }

    let Some(next) = Next::load(next_gipa, *instance) else {
        log!("Konnte Runtime-Funktionen nicht laden – Layer bleibt passiv");
        return res;
    };

    let app = CStr::from_ptr((*info).application_info.application_name.as_ptr()).to_string_lossy();
    log::set_app(&app);
    log!("Instanz erstellt für App: {app}");

    let mut g = state();
    g.next = Some(next);

    // Ausnahme-Liste aus den Optionen (Standard: wayvr)
    let process = config::process_name();
    if let Some(hit) = config::get().is_excluded(&[&app, &process]) {
        log!("„{app}“ ({process}) steht auf der Ausnahme-Liste („{hit}“) – ViewShot bleibt hier aus");
        return res;
    }

    match guard("prepare_paths", || prepare_paths(&next, *instance)).flatten() {
        Some((hands, profiles)) => {
            g.instances.insert(
                (*instance).into_raw(),
                Layer { hands, profiles, app_bindings: HashMap::new(), set_counter: 0, sessions: HashMap::new() },
            );
        }
        None => log!("Pfade konnten nicht erstellt werden – Layer bleibt passiv"),
    }
    log!("Aktive Instanzen: {}", g.instances.len());
    res
}

// ─────────────────────── Funktions-Weiche ───────────────────────

macro_rules! hook_table {
    ($name:expr, $out:expr, { $( $xr:literal => $f:ident : $ty:ident ),* $(,)? }) => {
        match $name {
            $( $xr => {
                *$out = Some(std::mem::transmute::<pfn::$ty, pfn::VoidFunction>($f));
                return xr::Result::SUCCESS;
            } )*
            _ => {}
        }
    };
}

unsafe extern "system" fn get_instance_proc_addr(
    instance: xr::Instance,
    name: *const c_char,
    out: *mut Option<pfn::VoidFunction>,
) -> xr::Result {
    if name.is_null() || out.is_null() {
        return xr::Result::ERROR_VALIDATION_FAILURE;
    }
    let n = CStr::from_ptr(name).to_bytes();
    hook_table!(n, out, {
        b"xrGetInstanceProcAddr" => get_instance_proc_addr: GetInstanceProcAddr,
        b"xrDestroyInstance" => destroy_instance: DestroyInstance,
        b"xrCreateSession" => create_session: CreateSession,
        b"xrDestroySession" => destroy_session: DestroySession,
        b"xrCreateSwapchain" => create_swapchain: CreateSwapchain,
        b"xrDestroySwapchain" => destroy_swapchain: DestroySwapchain,
        b"xrEnumerateSwapchainImages" => enumerate_swapchain_images: EnumerateSwapchainImages,
        b"xrAcquireSwapchainImage" => acquire_swapchain_image: AcquireSwapchainImage,
        b"xrReleaseSwapchainImage" => release_swapchain_image: ReleaseSwapchainImage,
        b"xrWaitFrame" => wait_frame: WaitFrame,
        b"xrEndFrame" => end_frame: EndFrame,
        b"xrSuggestInteractionProfileBindings" => suggest_bindings: SuggestInteractionProfileBindings,
        b"xrAttachSessionActionSets" => attach_action_sets: AttachSessionActionSets,
        b"xrSyncActions" => sync_actions: SyncActions,
    });
    match next() {
        Some(nx) => (nx.get_instance_proc_addr)(instance, name, out),
        None => xr::Result::ERROR_FUNCTION_UNSUPPORTED,
    }
}

// ─────────────────────── Instanz ───────────────────────

unsafe extern "system" fn destroy_instance(instance: xr::Instance) -> xr::Result {
    let nx = {
        let mut g = state();
        g.instances.remove(&instance.into_raw());
        g.next
    };
    log!("Instanz beendet");
    match nx {
        // Immer an die Runtime weitergeben – auch wenn wir die Instanz nicht kennen
        Some(nx) => (nx.destroy_instance)(instance),
        None => xr::Result::ERROR_HANDLE_INVALID,
    }
}

unsafe fn path(next: &Next, instance: xr::Instance, s: &str) -> Option<xr::Path> {
    let c = std::ffi::CString::new(s).ok()?;
    let mut p = xr::Path::NULL;
    ok((next.string_to_path)(instance, c.as_ptr(), &mut p)).then_some(p)
}

type Profiles = HashMap<xr::Path, Vec<(bindings::Slot, xr::Path)>>;

/// Wandelt alle Pfad-Texte aus bindings.rs einmal in XrPaths um.
unsafe fn prepare_paths(next: &Next, instance: xr::Instance) -> Option<([xr::Path; 2], Profiles)> {
    let hands = [
        path(next, instance, "/user/hand/left")?,
        path(next, instance, "/user/hand/right")?,
    ];
    let mut profiles = HashMap::new();
    for (profile, _, _) in bindings::PROFILES {
        let Some(p) = path(next, instance, profile) else { continue };
        let list: Vec<_> = bindings::for_profile(profile)
            .unwrap_or_default()
            .into_iter()
            .filter_map(|(slot, _hand, full)| Some((slot, path(next, instance, &full)?)))
            .collect();
        profiles.insert(p, list);
    }
    Some((hands, profiles))
}

/// Erstellt ein frisches Action-Set mit unseren 5 Actions.
unsafe fn create_actions(next: &Next, instance: xr::Instance, hands: [xr::Path; 2], n: u32) -> Option<Actions> {
    let mut set_info = xr::ActionSetCreateInfo {
        ty: xr::ActionSetCreateInfo::TYPE,
        next: std::ptr::null(),
        action_set_name: [0; xr::MAX_ACTION_SET_NAME_SIZE],
        localized_action_set_name: [0; xr::MAX_LOCALIZED_ACTION_SET_NAME_SIZE],
        priority: 0,
    };
    // Namen müssen pro Instanz eindeutig sein
    fill(&mut set_info.action_set_name, &format!("linuxvr_viewshot_{n}"));
    fill(&mut set_info.localized_action_set_name, &format!("LinuxVR-ViewShot {n}"));
    let mut set = xr::ActionSet::NULL;
    let r = (next.create_action_set)(instance, &set_info, &mut set);
    if !ok(r) {
        log!("xrCreateActionSet fehlgeschlagen: {r:?}");
        return None;
    }

    let make = |name: &str, label: &str, ty: xr::ActionType| -> Option<xr::Action> {
        let mut info = xr::ActionCreateInfo {
            ty: xr::ActionCreateInfo::TYPE,
            next: std::ptr::null(),
            action_name: [0; xr::MAX_ACTION_NAME_SIZE],
            action_type: ty,
            count_subaction_paths: 2,
            subaction_paths: hands.as_ptr(),
            localized_action_name: [0; xr::MAX_LOCALIZED_ACTION_NAME_SIZE],
        };
        fill(&mut info.action_name, name);
        fill(&mut info.localized_action_name, label);
        let mut a = xr::Action::NULL;
        let r = (next.create_action)(set, &info, &mut a);
        if !ok(r) {
            log!("xrCreateAction({name}) fehlgeschlagen: {r:?}");
            return None;
        }
        Some(a)
    };
    Some(Actions {
        set,
        grip: make("vs_grip", "ViewShot Grip", xr::ActionType::FLOAT_INPUT)?,
        trigger: make("vs_trigger", "ViewShot Trigger", xr::ActionType::FLOAT_INPUT)?,
        buttons: make("vs_buttons", "ViewShot Buttons", xr::ActionType::BOOLEAN_INPUT)?,
        pose: make("vs_hand_pose", "ViewShot Hand", xr::ActionType::POSE_INPUT)?,
        haptic: make("vs_haptic", "ViewShot Haptic", xr::ActionType::VIBRATION_OUTPUT)?,
        hands,
    })
}

// ─────────────────────── Eingaben ───────────────────────

/// Das Spiel schlägt Bindings vor. Wir geben sie UNVERÄNDERT weiter und
/// merken sie uns nur. Unsere eigenen Bindings kommen erst beim Anhängen
/// (attach) dazu – denn manche Spiele (z. B. VRChat/Unity) hängen an,
/// beenden die Session und schlagen DANACH neue Bindings vor.
unsafe extern "system" fn suggest_bindings(
    instance: xr::Instance,
    sb: *const xr::InteractionProfileSuggestedBinding,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    let r = (nx.suggest_interaction_profile_bindings)(instance, sb);
    if ok(r) && !sb.is_null() {
        let orig = &*sb;
        let list = if orig.suggested_bindings.is_null() {
            Vec::new()
        } else {
            std::slice::from_raw_parts(orig.suggested_bindings, orig.count_suggested_bindings as usize).to_vec()
        };
        if let Some(l) = state().instances.get_mut(&instance.into_raw()) {
            l.app_bindings.insert(orig.interaction_profile, list);
        }
    }
    r
}

unsafe fn suggest(nx: &Next, instance: xr::Instance, profile: xr::Path, list: &[xr::ActionSuggestedBinding]) -> xr::Result {
    let sb = xr::InteractionProfileSuggestedBinding {
        ty: xr::InteractionProfileSuggestedBinding::TYPE,
        next: std::ptr::null(),
        interaction_profile: profile,
        count_suggested_bindings: list.len() as u32,
        suggested_bindings: list.as_ptr(),
    };
    (nx.suggest_interaction_profile_bindings)(instance, &sb)
}

unsafe extern "system" fn attach_action_sets(
    session: xr::Session,
    info: *const xr::SessionActionSetsAttachInfo,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    if info.is_null() {
        return (nx.attach_session_action_sets)(session, info);
    }

    // Alles Nötige unter dem Lock einsammeln
    struct Prep {
        instance: xr::Instance,
        hands: [xr::Path; 2],
        n: u32,
        profiles: Profiles,
        app_bindings: HashMap<xr::Path, Vec<xr::ActionSuggestedBinding>>,
    }
    let prep = {
        let mut g = state();
        let found = g.instances.iter_mut().find(|(_, l)| l.sessions.contains_key(&session.into_raw()));
        match found {
            Some((inst, l)) if !l.sessions[&session.into_raw()].overlay => {
                l.set_counter += 1;
                Some(Prep {
                    instance: xr::Instance::from_raw(*inst),
                    hands: l.hands,
                    n: l.set_counter,
                    profiles: l.profiles.clone(),
                    app_bindings: l.app_bindings.clone(),
                })
            }
            _ => None,
        }
    };
    let Some(prep) = prep else {
        return (nx.attach_session_action_sets)(session, info);
    };

    // 1) Frisches Action-Set für diese Session
    let Some(actions) = guard("create_actions", || create_actions(&nx, prep.instance, prep.hands, prep.n)).flatten()
    else {
        return (nx.attach_session_action_sets)(session, info);
    };

    // 2) Für jedes Profil des Spiels: Bindings des Spiels + unsere neu vorschlagen
    let mut used = Vec::new();
    for (profile, app_list) in &prep.app_bindings {
        let Some(ours) = prep.profiles.get(profile) else { continue };
        let mut merged = app_list.clone();
        merged.extend(ours.iter().map(|(slot, p)| xr::ActionSuggestedBinding {
            action: actions.action_for(*slot),
            binding: *p,
        }));
        let r = suggest(&nx, prep.instance, *profile, &merged);
        if ok(r) {
            used.push(*profile);
        } else {
            log!("Bindings für ein Profil abgelehnt ({r:?})");
            suggest(&nx, prep.instance, *profile, app_list);
        }
    }
    if used.is_empty() {
        log!("Kein passendes Controller-Profil vom Spiel – Geste nicht verfügbar");
    }

    // 3) Anhängen: Sets des Spiels + unser Set
    let orig = &*info;
    let mut sets = std::slice::from_raw_parts(orig.action_sets, orig.count_action_sets as usize).to_vec();
    sets.push(actions.set);
    let mut copy = *orig;
    copy.count_action_sets = sets.len() as u32;
    copy.action_sets = sets.as_ptr();

    let r = (nx.attach_session_action_sets)(session, &copy);
    if !ok(r) {
        log!("Anhängen unseres Action-Sets fehlgeschlagen ({r:?}) – nur das Spiel");
        // Bindings des Spiels wiederherstellen, dann normal anhängen
        for profile in &used {
            suggest(&nx, prep.instance, *profile, &prep.app_bindings[profile]);
        }
        return (nx.attach_session_action_sets)(session, info);
    }

    // 4) Handpositionen als "Spaces" anlegen und alles merken
    guard("attach", || {
        let mut g = state();
        let Some(s) = g.session_mut(session) else { return };
        for (i, hand) in actions.hands.iter().enumerate() {
            let ci = xr::ActionSpaceCreateInfo {
                ty: xr::ActionSpaceCreateInfo::TYPE,
                next: std::ptr::null(),
                action: actions.pose,
                subaction_path: *hand,
                pose_in_action_space: xr::Posef {
                    orientation: xr::Quaternionf { x: 0.0, y: 0.0, z: 0.0, w: 1.0 },
                    position: xr::Vector3f { x: 0.0, y: 0.0, z: 0.0 },
                },
            };
            let r = (nx.create_action_space)(session, &ci, &mut s.spaces[i]);
            if !ok(r) {
                log!("xrCreateActionSpace fehlgeschlagen: {r:?}");
            }
        }
        s.actions = Some(actions);
        log!("Action-Set angehängt ({} Profil(e)) – Geste ist bereit", used.len());
    });
    r
}

unsafe fn get_float(nx: &Next, session: xr::Session, action: xr::Action, sub: xr::Path) -> f32 {
    let info = xr::ActionStateGetInfo {
        ty: xr::ActionStateGetInfo::TYPE,
        next: std::ptr::null(),
        action,
        subaction_path: sub,
    };
    let mut st: xr::ActionStateFloat = std::mem::zeroed();
    st.ty = xr::ActionStateFloat::TYPE;
    if ok((nx.get_action_state_float)(session, &info, &mut st)) && st.is_active.into() {
        st.current_state
    } else {
        0.0
    }
}

unsafe fn get_bool(nx: &Next, session: xr::Session, action: xr::Action) -> bool {
    let info = xr::ActionStateGetInfo {
        ty: xr::ActionStateGetInfo::TYPE,
        next: std::ptr::null(),
        action,
        subaction_path: xr::Path::NULL, // NULL = beide Hände zusammen
    };
    let mut st: xr::ActionStateBoolean = std::mem::zeroed();
    st.ty = xr::ActionStateBoolean::TYPE;
    ok((nx.get_action_state_boolean)(session, &info, &mut st))
        && bool::from(st.is_active)
        && bool::from(st.current_state)
}

unsafe fn locate(nx: &Next, space: xr::Space, base: xr::Space, time: xr::Time) -> Option<xr::Vector3f> {
    if space == xr::Space::NULL || base == xr::Space::NULL || time.as_nanos() == 0 {
        return None;
    }
    let mut loc: xr::SpaceLocation = std::mem::zeroed();
    loc.ty = xr::SpaceLocation::TYPE;
    if !ok((nx.locate_space)(space, base, time, &mut loc)) {
        return None;
    }
    loc.location_flags
        .contains(xr::SpaceLocationFlags::POSITION_VALID)
        .then_some(loc.pose.position)
}

unsafe fn vibrate(nx: &Next, session: xr::Session, a: &Actions, ms: i64, amplitude: f32) {
    let vib = xr::HapticVibration {
        ty: xr::HapticVibration::TYPE,
        next: std::ptr::null(),
        duration: xr::Duration::from_nanos(ms * 1_000_000),
        frequency: xr::FREQUENCY_UNSPECIFIED,
        amplitude,
    };
    for hand in a.hands {
        let info = xr::HapticActionInfo {
            ty: xr::HapticActionInfo::TYPE,
            next: std::ptr::null(),
            action: a.haptic,
            subaction_path: hand,
        };
        (nx.apply_haptic_feedback)(session, &info, &vib as *const _ as *const xr::HapticBaseHeader);
    }
}

unsafe extern "system" fn sync_actions(session: xr::Session, info: *const xr::ActionsSyncInfo) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    let our_set = state().session_mut(session).and_then(|s| s.actions.as_ref().map(|a| a.set));
    let (Some(our_set), false) = (our_set, info.is_null()) else {
        return (nx.sync_actions)(session, info);
    };

    // Unser Set zu den aktiven Sets des Spiels hinzufügen
    let orig = &*info;
    let mut active = if orig.active_action_sets.is_null() {
        Vec::new()
    } else {
        std::slice::from_raw_parts(orig.active_action_sets, orig.count_active_action_sets as usize).to_vec()
    };
    active.push(xr::ActiveActionSet { action_set: our_set, subaction_path: xr::Path::NULL });
    let mut copy = *orig;
    copy.count_active_action_sets = active.len() as u32;
    copy.active_action_sets = active.as_ptr();

    let r = (nx.sync_actions)(session, &copy);
    if !ok(r) {
        return (nx.sync_actions)(session, info);
    }
    if let Some(s) = state().session_mut(session) {
        if s.last_sync != r {
            log!("xrSyncActions: {r:?} (SUCCESS = Spiel hat Fokus)");
            s.last_sync = r;
        }
    }
    if r == xr::Result::SUCCESS {
        guard("sync", || update_gesture(&nx, session));
    }
    r
}

unsafe fn update_gesture(nx: &Next, session: xr::Session) {
    let mut g = state();
    let Some(s) = g.session_mut(session) else { return };
    let Some(a) = s.actions.as_ref() else { return };

    let left = locate(nx, s.spaces[0], s.spaces[1], s.last_time);
    let inputs = gesture::Inputs {
        grip: [get_float(nx, session, a.grip, a.hands[0]), get_float(nx, session, a.grip, a.hands[1])],
        trigger: [
            get_float(nx, session, a.trigger, a.hands[0]),
            get_float(nx, session, a.trigger, a.hands[1]),
        ],
        buttons: get_bool(nx, session, a.buttons),
        // Position der linken Hand relativ zur rechten = Abstand
        hand_distance: left.map(|p| (p.x * p.x + p.y * p.y + p.z * p.z).sqrt()),
    };

    let buttons = config::get().buttons();
    match s.gesture.update(&inputs, Instant::now(), &buttons) {
        gesture::Event::FrameActivated => {
            vibrate(nx, session, a, 40, 0.3);
            log!("Rahmen aktiv");
        }
        gesture::Event::TakePhoto => {
            vibrate(nx, session, a, 80, 0.8);
            s.capture_pending = true;
            s.pending_frames = 0;
            s.flash_until = Some(Instant::now() + std::time::Duration::from_millis(150));
            log!("Auslöser gedrückt (Session {}, bisher {} Frames)", session.into_raw(), s.frames);
        }
        gesture::Event::CycleType => {
            vibrate(nx, session, a, 25, 0.4);
            log!("Typ gewechselt: {}", icons::cycle().as_str());
        }
        gesture::Event::FrameClosed => log!("Rahmen geschlossen"),
        gesture::Event::None => {}
    }
}

// ─────────────────────── Session ───────────────────────

unsafe extern "system" fn create_session(
    instance: xr::Instance,
    info: *const xr::SessionCreateInfo,
    session: *mut xr::Session,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    let r = (nx.create_session)(instance, info, session);
    if !ok(r) {
        return r;
    }

    // In der "next"-Kette nach der Vulkan-Grafikbindung suchen
    let mut vk_binding = None;
    let mut overlay = false;
    let mut p = (*info).next as *const xr::BaseInStructure;
    while !p.is_null() {
        if (*p).ty == xr::StructureType::SESSION_CREATE_INFO_OVERLAY_EXTX {
            overlay = true;
        }
        if (*p).ty == xr::GraphicsBindingVulkanKHR::TYPE {
            let b = &*(p as *const xr::GraphicsBindingVulkanKHR);
            vk_binding = Some(VkBinding {
                instance: b.instance as usize,
                physical_device: b.physical_device as usize,
                device: b.device as usize,
                queue_family: b.queue_family_index,
                queue_index: b.queue_index,
            });
        }
        p = (*p).next;
    }
    if overlay {
        log!("Overlay-Session (z. B. WayVR) – ViewShot bleibt hier aus");
    } else if vk_binding.is_none() {
        log!("Keine Vulkan-Session – Fotos gehen (noch) nicht mit diesem Spiel");
    }

    if let Some(l) = state().instances.get_mut(&instance.into_raw()) {
        l.sessions.insert((*session).into_raw(), SessionData {
            actions: None,
            spaces: [xr::Space::NULL; 2],
            vk_binding,
            vk: None,
            vk_failed: false,
            swapchains: HashMap::new(),
            last_time: xr::Time::from_nanos(0),
            gesture: gesture::Gesture::new(),
            capture_pending: false,
            pending_frames: 0,
            frames: 0,
            overlay,
            last_sync: xr::Result::SUCCESS,
            frame_sc: None,
            frame_failed: false,
            icon_sc: None,
            icon_failed: false,
            flash_until: None,
        });
    }
    log!("Session gestartet: {}", (*session).into_raw());
    r
}

unsafe extern "system" fn destroy_session(session: xr::Session) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    log!("Session beendet: {}", session.into_raw());
    let own: Vec<xr::Swapchain> = state()
        .session_mut(session)
        .map(|s| [s.frame_sc.take(), s.icon_sc.take()].into_iter().flatten().collect())
        .unwrap_or_default();
    for sc in own {
        (nx.destroy_swapchain)(sc);
    }
    // Entfernen räumt auch den Vulkan-Kontext auf
    let removed = state().layer_of_session(session).and_then(|l| l.sessions.remove(&session.into_raw()));
    drop(removed);
    (nx.destroy_session)(session)
}

unsafe extern "system" fn wait_frame(
    session: xr::Session,
    info: *const xr::FrameWaitInfo,
    frame_state: *mut xr::FrameState,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    let r = (nx.wait_frame)(session, info, frame_state);
    if ok(r) && !frame_state.is_null() {
        if let Some(s) = state().session_mut(session) {
            s.last_time = (*frame_state).predicted_display_time;
        }
    }
    r
}

// ─────────────────────── Swapchains ───────────────────────

unsafe extern "system" fn create_swapchain(
    session: xr::Session,
    info: *const xr::SwapchainCreateInfo,
    swapchain: *mut xr::Swapchain,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    if info.is_null() {
        return (nx.create_swapchain)(session, info, swapchain);
    }
    let orig = &*info;

    // Farbbilder brauchen das TRANSFER_SRC-Flag, damit wir daraus kopieren dürfen
    let is_color = orig.usage_flags.contains(xr::SwapchainUsageFlags::COLOR_ATTACHMENT);
    let mut transfer_ok = orig.usage_flags.contains(xr::SwapchainUsageFlags::TRANSFER_SRC);
    let mut r = xr::Result::ERROR_RUNTIME_FAILURE;
    if is_color && !transfer_ok {
        let mut copy = *orig;
        copy.usage_flags |= xr::SwapchainUsageFlags::TRANSFER_SRC;
        r = (nx.create_swapchain)(session, &copy, swapchain);
        transfer_ok = ok(r);
    }
    if !transfer_ok || !is_color {
        r = (nx.create_swapchain)(session, info, swapchain);
    }
    if !ok(r) {
        return r;
    }

    if is_color {
        if let Some(s) = state().session_mut(session) {
            s.swapchains.insert(
                (*swapchain).into_raw(),
                SwapchainInfo {
                    format: orig.format,
                    sample_count: orig.sample_count,
                    transfer_ok,
                    images: Vec::new(),
                    acquired: VecDeque::new(),
                    last_released: None,
                },
            );
        }
    }
    r
}

unsafe extern "system" fn destroy_swapchain(swapchain: xr::Swapchain) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    for s in state().instances.values_mut().flat_map(|l| l.sessions.values_mut()) {
        s.swapchains.remove(&swapchain.into_raw());
    }
    (nx.destroy_swapchain)(swapchain)
}

unsafe extern "system" fn enumerate_swapchain_images(
    swapchain: xr::Swapchain,
    capacity: u32,
    count: *mut u32,
    images: *mut xr::SwapchainImageBaseHeader,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    let r = (nx.enumerate_swapchain_images)(swapchain, capacity, count, images);
    if ok(r) && !images.is_null() && capacity > 0 && (*images).ty == xr::SwapchainImageVulkanKHR::TYPE {
        let list = std::slice::from_raw_parts(images as *const xr::SwapchainImageVulkanKHR, *count as usize);
        if let Some(sc) = state().swapchain_mut(swapchain)
        {
            sc.images = list.iter().map(|i| i.image).collect();
        }
    }
    r
}

unsafe extern "system" fn acquire_swapchain_image(
    swapchain: xr::Swapchain,
    info: *const xr::SwapchainImageAcquireInfo,
    index: *mut u32,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    let r = (nx.acquire_swapchain_image)(swapchain, info, index);
    if ok(r) {
        if let Some(sc) = state().swapchain_mut(swapchain)
        {
            sc.acquired.push_back(*index);
        }
    }
    r
}

unsafe extern "system" fn release_swapchain_image(
    swapchain: xr::Swapchain,
    info: *const xr::SwapchainImageReleaseInfo,
) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    let r = (nx.release_swapchain_image)(swapchain, info);
    if ok(r) {
        if let Some(sc) = state().swapchain_mut(swapchain)
        {
            // Freigegeben wird immer das älteste geholte Bild
            sc.last_released = sc.acquired.pop_front();
        }
    }
    r
}

// ─────────────────────── Foto aufnehmen ───────────────────────

unsafe extern "system" fn end_frame(session: xr::Session, info: *const xr::FrameEndInfo) -> xr::Result {
    let Some(nx) = next() else { return xr::Result::ERROR_HANDLE_INVALID };
    if info.is_null() {
        return (nx.end_frame)(session, info);
    }
    // 1) Foto – nur aus den Ebenen des Spiels, der Rahmen ist also nie im Bild
    guard("capture", || try_capture(&nx, session, &*info));

    // 2) Sichtbarer Rahmen als zusätzliche Ebenen oben drauf
    let quads = guard("frame", || build_frame_quads(&nx, session, &*info)).unwrap_or_default();
    if quads.is_empty() {
        return (nx.end_frame)(session, info);
    }
    let orig = &*info;
    let mut layers: Vec<*const xr::CompositionLayerBaseHeader> = if orig.layers.is_null() {
        Vec::new()
    } else {
        std::slice::from_raw_parts(orig.layers, orig.layer_count as usize).to_vec()
    };
    layers.extend(quads.iter().map(|q| q as *const _ as *const xr::CompositionLayerBaseHeader));
    let mut copy = *orig;
    copy.layer_count = layers.len() as u32;
    copy.layers = layers.as_ptr();

    let r = (nx.end_frame)(session, &copy);
    if ok(r) {
        return r;
    }
    // Runtime mag unsere Ebenen nicht → Rahmen abschalten, Frame normal beenden
    log!("Rahmen-Ebenen abgelehnt ({r:?}) – Rahmen-Anzeige aus");
    if let Some(s) = state().session_mut(session) {
        s.frame_failed = true;
    }
    (nx.end_frame)(session, info)
}

/// Vulkan-Kontext beim ersten Bedarf anlegen. `false` = geht nicht.
unsafe fn ensure_vk(s: &mut SessionData) -> bool {
    if s.vk.is_none() && !s.vk_failed {
        let Some(b) = s.vk_binding else {
            log!("Keine Vulkan-Session – Foto/Rahmen nicht möglich");
            s.vk_failed = true;
            return false;
        };
        match capture::VkCtx::new(b.instance, b.physical_device, b.device, b.queue_family, b.queue_index) {
            Ok(ctx) => s.vk = Some(ctx),
            Err(e) => {
                log!("Vulkan-Start fehlgeschlagen: {e}");
                s.vk_failed = true;
            }
        }
    }
    s.vk.is_some()
}

/// Erste Projektions-Ebene eines Frames (= das normale 3D-Bild des Spiels)
unsafe fn find_projection(info: &xr::FrameEndInfo) -> Option<&xr::CompositionLayerProjection> {
    if info.layers.is_null() {
        return None;
    }
    std::slice::from_raw_parts(info.layers, info.layer_count as usize)
        .iter()
        .filter(|p| !p.is_null())
        .find(|p| (***p).ty == xr::CompositionLayerProjection::TYPE)
        .map(|p| &*(*p as *const xr::CompositionLayerProjection))
        .filter(|p| p.view_count > 0 && !p.views.is_null())
}

/// Ausschnitt für diesen Frame: (Bild, Ausschnitt, Mittelauge, FOV, Tiefe der Hände)
/// Welches Auge liefert das Foto, und von wo aus wird gemessen?
/// eye_mix (Optionen → ViewShot): 0 % = links, 100 % = rechts.
/// Die Pixel kommen immer aus EINEM Auge (zwei Bilder mischen gäbe
/// Doppelbilder) – bis 50 % links, darüber rechts. Der Blickpunkt für den
/// Ausschnitt wandert stufenlos zwischen den Augen.
unsafe fn choose_view(proj: &xr::CompositionLayerProjection, t: f32) -> (&xr::CompositionLayerProjectionView, xr::Posef) {
    let left = &*proj.views;
    if proj.view_count < 2 {
        return (left, left.pose);
    }
    let right = &*proj.views.add(1);
    let view = if t > 0.5 { right } else { left };
    (view, frame::blend_eye(&left.pose, &right.pose, t, view.pose.orientation))
}

fn image_rect(view: &xr::CompositionLayerProjectionView) -> frame::Rect {
    let r = view.sub_image.image_rect;
    frame::Rect { x: r.offset.x, y: r.offset.y, w: r.extent.width, h: r.extent.height }
}

unsafe fn frame_geometry(
    nx: &Next,
    s: &SessionData,
    proj: &xr::CompositionLayerProjection,
    time: xr::Time,
) -> Option<(frame::Rect, frame::Rect, xr::Posef, xr::Fovf, f32)> {
    let cfg = config::get();
    let (view, eye) = choose_view(proj, cfg.eye_t());
    let img = image_rect(view);
    let hand = |i: usize| locate(nx, s.spaces[i], proj.space, time).and_then(|p| frame::project(&eye, &view.fov, p));
    let (h0, h1) = (hand(0)?, hand(1)?);
    let rect = frame::crop_rect(img, &view.fov, Some(h0), Some(h1), cfg.inset_m());
    Some((img, rect, eye, view.fov, (h0.depth + h1.depth) * 0.5))
}

/// Legt eine STATISCHE Swapchain an (einmal füllen, immer benutzen).
/// `fill` bekommt Vulkan, das Bild und das gewählte Format.
unsafe fn make_static_swapchain(
    nx: &Next,
    session: xr::Session,
    vk: &capture::VkCtx,
    (width, height, layers): (u32, u32, u32),
    fill: &dyn Fn(&capture::VkCtx, ash::vk::Image, i64) -> Result<(), String>,
) -> Result<xr::Swapchain, String> {
    // Ein Farbformat wählen, das die Runtime kann
    let mut n = 0u32;
    (nx.enumerate_swapchain_formats)(session, 0, &mut n, std::ptr::null_mut());
    let mut formats = vec![0i64; n as usize];
    (nx.enumerate_swapchain_formats)(session, n, &mut n, formats.as_mut_ptr());
    let format = [save::R8G8B8A8_SRGB, save::B8G8R8A8_SRGB, save::R8G8B8A8_UNORM, save::B8G8R8A8_UNORM]
        .into_iter()
        .find(|f| formats.contains(f))
        .ok_or("kein passendes Format")?;

    let ci = xr::SwapchainCreateInfo {
        ty: xr::SwapchainCreateInfo::TYPE,
        next: std::ptr::null(),
        create_flags: xr::SwapchainCreateFlags::STATIC_IMAGE,
        usage_flags: xr::SwapchainUsageFlags::COLOR_ATTACHMENT | xr::SwapchainUsageFlags::TRANSFER_DST,
        format,
        sample_count: 1,
        width,
        height,
        face_count: 1,
        array_size: layers,
        mip_count: 1,
    };
    let mut sc = xr::Swapchain::NULL;
    let r = (nx.create_swapchain)(session, &ci, &mut sc);
    if !ok(r) {
        return Err(format!("xrCreateSwapchain: {r:?}"));
    }

    let fail = |msg: String| {
        (nx.destroy_swapchain)(sc);
        Err(msg)
    };
    let mut img: xr::SwapchainImageVulkanKHR = std::mem::zeroed();
    img.ty = xr::SwapchainImageVulkanKHR::TYPE;
    let mut count = 0u32;
    let r = (nx.enumerate_swapchain_images)(sc, 1, &mut count, &mut img as *mut _ as *mut xr::SwapchainImageBaseHeader);
    if !ok(r) || count == 0 {
        return fail(format!("Bilder: {r:?}"));
    }
    let mut idx = 0u32;
    let r = (nx.acquire_swapchain_image)(sc, std::ptr::null(), &mut idx);
    if !ok(r) {
        return fail(format!("acquire: {r:?}"));
    }
    let wait = xr::SwapchainImageWaitInfo {
        ty: xr::SwapchainImageWaitInfo::TYPE,
        next: std::ptr::null(),
        timeout: xr::Duration::INFINITE,
    };
    (nx.wait_swapchain_image)(sc, &wait);

    use ash::vk::Handle as _;
    let filled = fill(vk, ash::vk::Image::from_raw(img.image), format);
    (nx.release_swapchain_image)(sc, std::ptr::null());
    match filled {
        Ok(()) => Ok(sc),
        Err(e) => fail(e),
    }
}

/// Legt die kleine Swapchain für den Rahmen an und färbt sie ein (einmalig).
/// Ebene 0 = rot, 1 = weiß (Blitz)
unsafe fn ensure_frame_swapchain(nx: &Next, session: xr::Session, s: &mut SessionData) -> Option<xr::Swapchain> {
    if let Some(sc) = s.frame_sc {
        return Some(sc);
    }
    if s.frame_failed || !ensure_vk(s) {
        return None;
    }
    let vk = s.vk.as_ref()?;
    let red = [1.0, 0.05, 0.05, 1.0];
    let white = [1.0, 1.0, 1.0, 1.0];
    match make_static_swapchain(nx, session, vk, (4, 4, 2), &|vk, image, _| vk.fill_layers(image, &[red, white])) {
        Ok(sc) => {
            log!("Rahmen-Anzeige bereit");
            s.frame_sc = Some(sc);
            Some(sc)
        }
        Err(e) => {
            log!("Rahmen-Anzeige nicht möglich: {e}");
            s.frame_failed = true;
            None
        }
    }
}

/// Swapchain mit den drei Typ-Symbolen (Bild / Text / QR) – einmalig.
unsafe fn ensure_icon_swapchain(nx: &Next, session: xr::Session, s: &mut SessionData) -> Option<xr::Swapchain> {
    if let Some(sc) = s.icon_sc {
        return Some(sc);
    }
    if s.icon_failed || !ensure_vk(s) {
        return None;
    }
    let vk = s.vk.as_ref()?;
    let size = icons::ICON_SIZE;
    let fill = |vk: &capture::VkCtx, image, format| {
        let bgr = matches!(format, save::B8G8R8A8_SRGB | save::B8G8R8A8_UNORM);
        vk.upload_layers(image, &icons::pixels(bgr)?, size, size)
    };
    match make_static_swapchain(nx, session, vk, (size, size, icons::PhotoType::ALL.len() as u32), &fill) {
        Ok(sc) => {
            log!("Typ-Symbole bereit");
            s.icon_sc = Some(sc);
            Some(sc)
        }
        Err(e) => {
            log!("Typ-Symbole nicht möglich: {e}");
            s.icon_failed = true;
            None
        }
    }
}

/// Baut die 4 roten Linien des Rahmens für diesen Frame (leer = nichts zeigen).
unsafe fn build_frame_quads(nx: &Next, session: xr::Session, info: &xr::FrameEndInfo) -> Vec<xr::CompositionLayerQuad> {
    let mut g = state();
    let Some(s) = g.session_mut(session) else { return Vec::new() };
    let now = Instant::now();
    let flash = s.flash_until.is_some_and(|t| now < t);
    let active = matches!(
        s.gesture.state,
        gesture::State::Active | gesture::State::Pressing(..) | gesture::State::Cooldown
    );
    if s.actions.is_none() || !(active || flash) {
        return Vec::new();
    }
    let Some(proj) = find_projection(info) else { return Vec::new() };
    let Some((img, rect, eye, fov, depth)) = frame_geometry(nx, s, proj, info.display_time) else {
        return Vec::new();
    };
    if rect == img {
        return Vec::new(); // Hände zu nah beieinander / außerhalb
    }
    let Some(sc) = ensure_frame_swapchain(nx, session, s) else { return Vec::new() };

    let quad = |e: &frame::EdgeQuad, swapchain: xr::Swapchain, px: i32, layer: u32| xr::CompositionLayerQuad {
        ty: xr::CompositionLayerQuad::TYPE,
        next: std::ptr::null(),
        layer_flags: xr::CompositionLayerFlags::EMPTY,
        space: proj.space,
        eye_visibility: xr::EyeVisibility::BOTH,
        sub_image: xr::SwapchainSubImage {
            swapchain,
            image_rect: xr::Rect2Di {
                offset: xr::Offset2Di { x: 0, y: 0 },
                extent: xr::Extent2Di { width: px, height: px },
            },
            image_array_index: layer,
        },
        pose: e.pose,
        size: xr::Extent2Df { width: e.width, height: e.height },
    };

    // Linienstärke wächst mit der Entfernung → wirkt immer gleich dick
    let thickness = depth * 0.008;
    let mut quads: Vec<_> = frame::edge_quads(&eye, &fov, img, rect, depth, thickness)
        .iter()
        .map(|e| quad(e, sc, 4, if flash { 1 } else { 0 }))
        .collect();

    // Manueller Modus: Typ-Symbol innen unten rechts im Rahmen
    if config::get().buttons().mode.is_some() {
        if let Some(icon_sc) = ensure_icon_swapchain(nx, session, s) {
            // ~5° groß, aber höchstens ein Viertel des Rahmens
            let (w, h) = frame_size_m(&fov, img, rect, depth);
            let size = (depth * 0.09).min(w.min(h) * 0.25);
            let e = frame::corner_quad(&eye, &fov, img, rect, depth, size, thickness * 1.5);
            quads.push(quad(&e, icon_sc, icons::ICON_SIZE as i32, icons::current().index()));
        }
    }
    quads
}

/// Breite/Höhe des Rahmens in Metern (in Tiefe `depth`)
fn frame_size_m(fov: &xr::Fovf, img: frame::Rect, rect: frame::Rect, depth: f32) -> (f32, f32) {
    let w = rect.w as f32 / img.w as f32 * (fov.angle_right.tan() - fov.angle_left.tan()) * depth;
    let h = rect.h as f32 / img.h as f32 * (fov.angle_up.tan() - fov.angle_down.tan()) * depth;
    (w, h)
}

unsafe fn try_capture(nx: &Next, session: xr::Session, info: &xr::FrameEndInfo) {
    let mut g = state();
    let Some(s) = g.session_mut(session) else {
        // Diagnose: Wartet eine ANDERE Session auf ein Foto?
        let waiting: Vec<u64> = g
            .instances
            .values()
            .flat_map(|l| l.sessions.iter())
            .filter(|(_, s)| s.capture_pending)
            .map(|(k, _)| *k)
            .collect();
        if !waiting.is_empty() {
            log!("xrEndFrame auf unbekannter Session {} – Foto wartet auf {:?}", session.into_raw(), waiting);
        }
        return;
    };
    s.frames += 1;
    if s.frames == 1 {
        log!("Erster Frame auf Session {}", session.into_raw());
    }
    if !s.capture_pending {
        return;
    }
    s.pending_frames += 1;
    // Nach ~2 s ohne passendes Bild aufgeben (sonst hängt es ewig)
    if s.pending_frames > 180 {
        log!("Aufgegeben: 180 Frames ohne 3D-Bild");
        s.capture_pending = false;
        return;
    }
    if info.layers.is_null() || info.layer_count == 0 {
        if s.pending_frames == 1 {
            log!("Frame ohne Ebenen – warte auf nächsten");
        }
        return;
    }

    // Erste Projektions-Ebene suchen (= das normale 3D-Bild des Spiels)
    let layers = std::slice::from_raw_parts(info.layers, info.layer_count as usize);
    let Some(proj) = layers
        .iter()
        .filter(|p| !p.is_null())
        .find(|p| (***p).ty == xr::CompositionLayerProjection::TYPE)
        .map(|p| &*(*p as *const xr::CompositionLayerProjection))
    else {
        if s.pending_frames == 1 {
            let types: Vec<String> = layers
                .iter()
                .filter(|p| !p.is_null())
                .map(|p| format!("{:?}", (**p).ty))
                .collect();
            log!("Keine Projektions-Ebene, nur: {types:?}");
        }
        return; // beim nächsten Frame nochmal versuchen
    };
    s.capture_pending = false;
    log!("Projektions-Ebene gefunden nach {} Frame(s), {} Views", s.pending_frames, proj.view_count);
    if proj.view_count == 0 || proj.views.is_null() {
        log!("Projektions-Ebene ohne Views – kein Foto");
        return;
    }
    // Auge wählen (Optionen → ViewShot) und Hände ins Bild projizieren → Ausschnitt
    let cfg = config::get();
    let (view, eye) = choose_view(proj, cfg.eye_t());
    let sub = view.sub_image;
    let img = image_rect(view);
    let hand = |i: usize| {
        locate(nx, s.spaces[i], proj.space, info.display_time).and_then(|p| frame::project(&eye, &view.fov, p))
    };
    let (h0, h1) = (hand(0), hand(1));
    let inset = cfg.inset_m();
    let rect = frame::crop_rect(img, &view.fov, h0, h1, inset);
    log!(
        "Bild {img:?}, Hände {h0:?} {h1:?}, Rand {:.0} cm, Auge {:.0} % rechts → Ausschnitt {rect:?}",
        inset * 100.0,
        cfg.eye_mix
    );

    let Some(sc) = s.swapchains.get(&sub.swapchain.into_raw()) else {
        log!("Swapchain unbekannt – kein Foto");
        return;
    };
    if !save::is_supported(sc.format) {
        log!("Bildformat {} wird noch nicht unterstützt", sc.format);
        return;
    }
    if !sc.transfer_ok || sc.sample_count > 1 {
        log!("Swapchain erlaubt kein Kopieren (transfer={}, samples={})", sc.transfer_ok, sc.sample_count);
        return;
    }
    let Some(image) = sc.last_released.and_then(|i| sc.images.get(i as usize)).copied() else {
        log!("Kein freigegebenes Bild gefunden");
        return;
    };
    let format = sc.format;

    if !ensure_vk(s) {
        return;
    }
    let Some(vk) = s.vk.as_ref() else { return };

    use ash::vk::Handle as _;
    let started = Instant::now();
    match vk.copy_region(
        ash::vk::Image::from_raw(image),
        sub.image_array_index,
        (rect.x, rect.y, rect.w as u32, rect.h as u32),
    ) {
        Ok(raw) => {
            log!("Bild kopiert in {:?} ({}x{})", started.elapsed(), rect.w, rect.h);
            // manueller Modus → gewählten Typ ins PNG schreiben
            let photo_type = cfg.buttons().mode.is_some().then(|| icons::current().as_str());
            save::save_png_async(raw, format, rect.w as u32, rect.h as u32, photo_type);
        }
        Err(e) => log!("Kopieren fehlgeschlagen: {e}"),
    }
}

#[cfg(test)]
mod tests_mock;
