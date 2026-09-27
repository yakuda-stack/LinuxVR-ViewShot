//! Tabelle mit den "nächsten" OpenXR-Funktionen.
//!
//! Ein API-Layer sitzt zwischen Spiel und Runtime (WiVRn/Monado):
//!
//!   Spiel ──► unser Layer ──► (weitere Layer) ──► Runtime
//!
//! Wenn wir eine Funktion abfangen, müssen wir am Ende fast immer die
//! "nächste" Version aufrufen, sonst passiert im Spiel nichts. Diese
//! Zeiger holen wir einmal beim Erstellen der Instanz und merken sie uns hier.

use openxr_sys as xr;
use openxr_sys::pfn;
use std::ffi::CString;

/// Holt eine Funktion aus der nächsten Schicht.
///
/// UNSAFE: Wir rufen einen C-Funktionszeiger auf und wandeln danach einen
/// generischen Funktionszeiger in den richtigen Typ um (`transmute`).
/// Das ist nur korrekt, wenn `T` wirklich zur Funktion mit Namen `name`
/// passt – darum nutzen wir das nur im Makro unten mit den passenden Typen.
unsafe fn load<T: Copy>(gipa: pfn::GetInstanceProcAddr, instance: xr::Instance, name: &str) -> Option<T> {
    let cname = CString::new(name).ok()?;
    let mut f: Option<pfn::VoidFunction> = None;
    let res = gipa(instance, cname.as_ptr(), &mut f);
    if res != xr::Result::SUCCESS {
        return None;
    }
    // Ein Funktionszeiger ist immer gleich groß – egal welche Signatur.
    f.map(|f| std::mem::transmute_copy::<pfn::VoidFunction, T>(&f))
}

macro_rules! next_table {
    ($( $field:ident : $ty:ident = $name:literal ),* $(,)?) => {
        #[derive(Clone, Copy)]
        pub struct Next {
            pub get_instance_proc_addr: pfn::GetInstanceProcAddr,
            $( pub $field: pfn::$ty, )*
        }

        impl Next {
            /// Lädt alle Funktionen. `None`, wenn eine fehlt.
            pub unsafe fn load(gipa: pfn::GetInstanceProcAddr, instance: xr::Instance) -> Option<Self> {
                Some(Self {
                    get_instance_proc_addr: gipa,
                    $( $field: match load::<pfn::$ty>(gipa, instance, $name) {
                        Some(f) => f,
                        None => { crate::log!("Funktion fehlt in der Runtime: {}", $name); return None; }
                    }, )*
                })
            }
        }
    };
}

next_table! {
    destroy_instance: DestroyInstance = "xrDestroyInstance",
    create_session: CreateSession = "xrCreateSession",
    destroy_session: DestroySession = "xrDestroySession",
    create_swapchain: CreateSwapchain = "xrCreateSwapchain",
    destroy_swapchain: DestroySwapchain = "xrDestroySwapchain",
    enumerate_swapchain_images: EnumerateSwapchainImages = "xrEnumerateSwapchainImages",
    enumerate_swapchain_formats: EnumerateSwapchainFormats = "xrEnumerateSwapchainFormats",
    acquire_swapchain_image: AcquireSwapchainImage = "xrAcquireSwapchainImage",
    wait_swapchain_image: WaitSwapchainImage = "xrWaitSwapchainImage",
    release_swapchain_image: ReleaseSwapchainImage = "xrReleaseSwapchainImage",
    wait_frame: WaitFrame = "xrWaitFrame",
    end_frame: EndFrame = "xrEndFrame",
    string_to_path: StringToPath = "xrStringToPath",
    create_action_set: CreateActionSet = "xrCreateActionSet",
    create_action: CreateAction = "xrCreateAction",
    suggest_interaction_profile_bindings: SuggestInteractionProfileBindings = "xrSuggestInteractionProfileBindings",
    attach_session_action_sets: AttachSessionActionSets = "xrAttachSessionActionSets",
    sync_actions: SyncActions = "xrSyncActions",
    get_action_state_float: GetActionStateFloat = "xrGetActionStateFloat",
    get_action_state_boolean: GetActionStateBoolean = "xrGetActionStateBoolean",
    create_action_space: CreateActionSpace = "xrCreateActionSpace",
    locate_space: LocateSpace = "xrLocateSpace",
    apply_haptic_feedback: ApplyHapticFeedback = "xrApplyHapticFeedback",
}
