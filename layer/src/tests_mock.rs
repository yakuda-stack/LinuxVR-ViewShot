//! Test mit einer Fake-Runtime: prüft, dass der Layer unsere Bindings
//! und unser Action-Set korrekt an die Aufrufe des Spiels anhängt.

use super::*;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};

static SUGGEST_COUNT: AtomicU32 = AtomicU32::new(0);
static ATTACH_COUNT: AtomicU32 = AtomicU32::new(0);
static SYNC_COUNT: AtomicU32 = AtomicU32::new(0);
static COUNTER: AtomicU64 = AtomicU64::new(100);
static DESTROYED: AtomicU32 = AtomicU32::new(0);

/// Fake-Runtime merkt sich wie Monado: Action → Set, und welche Sets angehängt sind
static ACTION_SET_OF: LazyLock<Mutex<HashMap<u64, u64>>> = LazyLock::new(Default::default);
static ATTACHED_SETS: LazyLock<Mutex<Vec<u64>>> = LazyLock::new(Default::default);

unsafe extern "system" fn f_destroy_instance(_: xr::Instance) -> xr::Result {
    DESTROYED.fetch_add(1, Ordering::SeqCst);
    xr::Result::SUCCESS
}

unsafe extern "system" fn f_string_to_path(_: xr::Instance, _: *const c_char, p: *mut xr::Path) -> xr::Result {
    *p = xr::Path::from_raw(COUNTER.fetch_add(1, Ordering::SeqCst));
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_create_action_set(_: xr::Instance, _: *const xr::ActionSetCreateInfo, s: *mut xr::ActionSet) -> xr::Result {
    *s = xr::ActionSet::from_raw(COUNTER.fetch_add(1, Ordering::SeqCst));
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_create_action(set: xr::ActionSet, _: *const xr::ActionCreateInfo, a: *mut xr::Action) -> xr::Result {
    *a = xr::Action::from_raw(COUNTER.fetch_add(1, Ordering::SeqCst));
    ACTION_SET_OF.lock().unwrap().insert((*a).into_raw(), set.into_raw());
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_suggest(_: xr::Instance, s: *const xr::InteractionProfileSuggestedBinding) -> xr::Result {
    // Wie die echte Runtime: Bindings für schon angehängte Sets → Fehler
    let list = std::slice::from_raw_parts((*s).suggested_bindings, (*s).count_suggested_bindings as usize);
    let map = ACTION_SET_OF.lock().unwrap();
    let attached = ATTACHED_SETS.lock().unwrap();
    if list.iter().any(|b| map.get(&b.action.into_raw()).is_some_and(|set| attached.contains(set))) {
        return xr::Result::ERROR_ACTIONSETS_ALREADY_ATTACHED;
    }
    SUGGEST_COUNT.store((*s).count_suggested_bindings, Ordering::SeqCst);
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_attach(_: xr::Session, i: *const xr::SessionActionSetsAttachInfo) -> xr::Result {
    ATTACH_COUNT.store((*i).count_action_sets, Ordering::SeqCst);
    let sets = std::slice::from_raw_parts((*i).action_sets, (*i).count_action_sets as usize);
    ATTACHED_SETS.lock().unwrap().extend(sets.iter().map(|s| s.into_raw()));
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_sync(_: xr::Session, i: *const xr::ActionsSyncInfo) -> xr::Result {
    SYNC_COUNT.store((*i).count_active_action_sets, Ordering::SeqCst);
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_create_session(_: xr::Instance, _: *const xr::SessionCreateInfo, s: *mut xr::Session) -> xr::Result {
    *s = xr::Session::from_raw(COUNTER.fetch_add(1, Ordering::SeqCst));
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_generic() -> xr::Result {
    xr::Result::SUCCESS
}
unsafe extern "system" fn f_create_instance(_: *const xr::InstanceCreateInfo, _: *const xr::ApiLayerCreateInfo, i: *mut xr::Instance) -> xr::Result {
    *i = xr::Instance::from_raw(COUNTER.fetch_add(1, Ordering::SeqCst));
    xr::Result::SUCCESS
}

unsafe extern "system" fn fake_gipa(_: xr::Instance, name: *const c_char, out: *mut Option<pfn::VoidFunction>) -> xr::Result {
    let n = CStr::from_ptr(name).to_str().unwrap();
    let f: pfn::VoidFunction = match n {
        "xrStringToPath" => std::mem::transmute::<pfn::StringToPath, pfn::VoidFunction>(f_string_to_path),
        "xrCreateActionSet" => std::mem::transmute::<pfn::CreateActionSet, pfn::VoidFunction>(f_create_action_set),
        "xrCreateAction" => std::mem::transmute::<pfn::CreateAction, pfn::VoidFunction>(f_create_action),
        "xrSuggestInteractionProfileBindings" => std::mem::transmute::<pfn::SuggestInteractionProfileBindings, pfn::VoidFunction>(f_suggest),
        "xrAttachSessionActionSets" => std::mem::transmute::<pfn::AttachSessionActionSets, pfn::VoidFunction>(f_attach),
        "xrSyncActions" => std::mem::transmute::<pfn::SyncActions, pfn::VoidFunction>(f_sync),
        "xrDestroyInstance" => std::mem::transmute::<pfn::DestroyInstance, pfn::VoidFunction>(f_destroy_instance),
        "xrCreateSession" => std::mem::transmute::<pfn::CreateSession, pfn::VoidFunction>(f_create_session),
        _ => std::mem::transmute::<unsafe extern "system" fn() -> xr::Result, pfn::VoidFunction>(f_generic),
    };
    *out = Some(f);
    xr::Result::SUCCESS
}

/// Loader-Verhandlung + neue Instanz über unseren Layer
unsafe fn new_instance() -> xr::Instance {
        // 1) Loader-Verhandlung
        let li = xr::NegotiateLoaderInfo {
            struct_type: xr::NegotiateLoaderInfo::TYPE,
            struct_version: 1,
            struct_size: std::mem::size_of::<xr::NegotiateLoaderInfo>(),
            min_interface_version: 1,
            max_interface_version: 1,
            min_api_version: xr::Version::new(1, 0, 0),
            max_api_version: xr::Version::new(1, 1, 0),
        };
        let mut req: xr::NegotiateApiLayerRequest = std::mem::zeroed();
        req.struct_type = xr::NegotiateApiLayerRequest::TYPE;
        assert_eq!(xrNegotiateLoaderApiLayerInterface(&li, std::ptr::null(), &mut req), xr::Result::SUCCESS);

        // 2) Instanz über unseren Layer erstellen
        let mut next_info: xr::ApiLayerNextInfo = std::mem::zeroed();
        next_info.struct_type = xr::ApiLayerNextInfo::TYPE;
        next_info.next_get_instance_proc_addr = Some(fake_gipa);
        next_info.next_create_api_layer_instance = Some(f_create_instance);
        let mut layer_info: xr::ApiLayerCreateInfo = std::mem::zeroed();
        layer_info.struct_type = xr::ApiLayerCreateInfo::TYPE;
        layer_info.next_info = &mut next_info;
        let mut ci: xr::InstanceCreateInfo = std::mem::zeroed();
        ci.ty = xr::InstanceCreateInfo::TYPE;
        let mut inst = xr::Instance::NULL;
        let create = req.create_api_layer_instance.unwrap();
        assert_eq!(create(&ci, &layer_info, &mut inst), xr::Result::SUCCESS);
        inst
}

/// Beide Tests teilen den globalen Zustand → nacheinander ausführen
static SERIAL: Mutex<()> = Mutex::new(());

unsafe fn suggest_app(inst: xr::Instance, profile: xr::Path, app: &[xr::ActionSuggestedBinding]) -> xr::Result {
    let sb = xr::InteractionProfileSuggestedBinding {
        ty: xr::InteractionProfileSuggestedBinding::TYPE,
        next: std::ptr::null(),
        interaction_profile: profile,
        count_suggested_bindings: app.len() as u32,
        suggested_bindings: app.as_ptr(),
    };
    suggest_bindings(inst, &sb)
}

unsafe fn session_and_attach(inst: xr::Instance, app_set: xr::ActionSet) -> xr::Session {
    let mut sci: xr::SessionCreateInfo = std::mem::zeroed();
    sci.ty = xr::SessionCreateInfo::TYPE;
    let mut sess = xr::Session::NULL;
    assert_eq!(create_session(inst, &sci, &mut sess), xr::Result::SUCCESS);
    let sets = [app_set];
    let ai = xr::SessionActionSetsAttachInfo {
        ty: xr::SessionActionSetsAttachInfo::TYPE,
        next: std::ptr::null(),
        count_action_sets: 1,
        action_sets: sets.as_ptr(),
    };
    assert_eq!(attach_action_sets(sess, &ai), xr::Result::SUCCESS);
    sess
}

/// Nachbau der VRChat/Unity-Reihenfolge aus dem Log:
/// Vorschlagen → Session A + Anhängen → Session A weg →
/// NEU vorschlagen → Session B + Anhängen. Unsere Actions müssen in B gebunden sein.
#[test]
fn chain_with_fake_runtime() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    unsafe {
        let inst = new_instance();
        let profiles = state().instances[&inst.into_raw()].profiles.clone();
        let touch = *profiles.keys().find(|p| profiles[*p].len() == 14).unwrap();
        let app = [xr::ActionSuggestedBinding { action: xr::Action::from_raw(1), binding: xr::Path::from_raw(2) }; 2];

        // Vorschlag des Spiels geht unverändert durch
        assert_eq!(suggest_app(inst, touch, &app), xr::Result::SUCCESS);
        assert_eq!(SUGGEST_COUNT.load(Ordering::SeqCst), 2);

        // Session A: beim Anhängen kommen unsere 14 Bindings dazu
        let a = session_and_attach(inst, xr::ActionSet::from_raw(99));
        assert_eq!(SUGGEST_COUNT.load(Ordering::SeqCst), 16);
        assert_eq!(ATTACH_COUNT.load(Ordering::SeqCst), 2);
        assert_eq!(destroy_session(a), xr::Result::SUCCESS);

        // Spiel schlägt erneut vor (neue eigene Actions) → darf NICHT scheitern
        let app2 = [xr::ActionSuggestedBinding { action: xr::Action::from_raw(3), binding: xr::Path::from_raw(2) }; 2];
        assert_eq!(suggest_app(inst, touch, &app2), xr::Result::SUCCESS);

        // Session B: frisches Set, wieder 16 Bindings, wieder 2 Sets
        let b = session_and_attach(inst, xr::ActionSet::from_raw(98));
        assert_eq!(SUGGEST_COUNT.load(Ordering::SeqCst), 16);
        assert_eq!(ATTACH_COUNT.load(Ordering::SeqCst), 2);
        assert!(state().session_mut(b).unwrap().actions.is_some());

        let active = [xr::ActiveActionSet { action_set: xr::ActionSet::from_raw(98), subaction_path: xr::Path::NULL }];
        let si = xr::ActionsSyncInfo {
            ty: xr::ActionsSyncInfo::TYPE,
            next: std::ptr::null(),
            count_active_action_sets: 1,
            active_action_sets: active.as_ptr(),
        };
        assert_eq!(sync_actions(b, &si), xr::Result::SUCCESS);
        assert_eq!(SYNC_COUNT.load(Ordering::SeqCst), 2);
    }
}

/// Genau das Szenario aus dem wineopenxr-Log: mehrere Instanzen gleichzeitig,
/// in "falscher" Reihenfolge beendet. Jede muss an die Runtime gehen.
#[test]
fn overlapping_instances() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    unsafe {
        let before = DESTROYED.load(Ordering::SeqCst);
        let a = new_instance();
        let b = new_instance();
        assert_eq!(destroy_instance(a), xr::Result::SUCCESS);
        let c = new_instance();
        assert!(state().instances.contains_key(&b.into_raw()));
        assert_eq!(destroy_instance(c), xr::Result::SUCCESS);
        assert_eq!(destroy_instance(b), xr::Result::SUCCESS);
        assert_eq!(DESTROYED.load(Ordering::SeqCst) - before, 3);
        // Auch ohne bekannte Instanz wird weitergereicht
        let mut sess = xr::Session::NULL;
        let mut sci: xr::SessionCreateInfo = std::mem::zeroed();
        sci.ty = xr::SessionCreateInfo::TYPE;
        assert_eq!(create_session(xr::Instance::from_raw(999), &sci, &mut sess), xr::Result::SUCCESS);
    }
}
