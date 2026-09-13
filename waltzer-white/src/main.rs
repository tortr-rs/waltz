//! waltzer-white: a minimal video-wallpaper renderer for wlr-layer-shell
//! compositors, replacing Waltz's mpvpaper dependency.
//!
//! Scope, deliberately: one file, looped, muted, hardware decode on, no
//! option passthrough, no config file, no IPC beyond process start/kill.
//! One shared decode (one libmpv render context), fanned out to one or
//! more outputs from a single process — cloning a wallpaper to N monitors
//! shouldn't cost N independent decodes of the same file.

use std::env;
use std::ffi::c_void;
use std::path::Path;
use std::process::ExitCode;
use std::rc::Rc;

use libmpv2::Mpv;
use libmpv2::render::{OpenGLInitParams, RenderParam, RenderParamApiType};
use wayland_client::protocol::{wl_callback, wl_compositor, wl_output, wl_registry, wl_surface};
use wayland_client::{Connection, Dispatch, Proxy, QueueHandle};
use wayland_protocols_wlr::layer_shell::v1::client::{zwlr_layer_shell_v1, zwlr_layer_surface_v1};

/// Per-output state. Every target shares the same EGL context and the same
/// mpv render context — only the Wayland surface, the EGL window/surface,
/// and the configured size are per-output.
struct OutputTarget {
    name: String,
    output: Option<wl_output::WlOutput>,
    wl_surface: Option<wl_surface::WlSurface>,
    layer_surface: Option<zwlr_layer_surface_v1::ZwlrLayerSurfaceV1>,
    width: i32,
    height: i32,
    configured: bool,
    closed: bool,
    need_redraw: bool,
    // Must stay alive as long as egl_surface references it.
    _egl_window: Option<wayland_egl::WlEglSurface>,
    egl_surface: Option<khronos_egl::Surface>,
}

impl OutputTarget {
    fn new(name: String) -> Self {
        OutputTarget {
            name,
            output: None,
            wl_surface: None,
            layer_surface: None,
            width: 0,
            height: 0,
            configured: false,
            closed: false,
            need_redraw: false,
            _egl_window: None,
            egl_surface: None,
        }
    }
}

struct State {
    compositor: Option<wl_compositor::WlCompositor>,
    layer_shell: Option<zwlr_layer_shell_v1::ZwlrLayerShellV1>,
    targets: Vec<OutputTarget>,
}

impl Dispatch<wl_registry::WlRegistry, ()> for State {
    fn event(
        state: &mut Self,
        registry: &wl_registry::WlRegistry,
        event: wl_registry::Event,
        _: &(),
        _: &Connection,
        qh: &QueueHandle<Self>,
    ) {
        if let wl_registry::Event::Global { name, interface, version } = event {
            match interface.as_str() {
                "wl_compositor" => {
                    state.compositor =
                        Some(registry.bind::<wl_compositor::WlCompositor, _, _>(name, version.min(4), qh, ()));
                }
                "zwlr_layer_shell_v1" => {
                    state.layer_shell = Some(registry.bind::<zwlr_layer_shell_v1::ZwlrLayerShellV1, _, _>(
                        name,
                        version.min(4),
                        qh,
                        (),
                    ));
                }
                "wl_output" => {
                    // wl_output.name requires interface version >= 4. Dropping this
                    // handle doesn't destroy the object or stop its events, so
                    // binding it is enough; the Dispatch impl below matches it
                    // against our target list once its Name event arrives.
                    registry.bind::<wl_output::WlOutput, _, _>(name, version.min(4), qh, ());
                }
                _ => {}
            }
        }
    }
}

impl Dispatch<wl_output::WlOutput, ()> for State {
    fn event(
        state: &mut Self,
        proxy: &wl_output::WlOutput,
        event: wl_output::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if let wl_output::Event::Name { name } = event {
            for t in state.targets.iter_mut() {
                if t.name == name && t.output.is_none() {
                    t.output = Some(proxy.clone());
                    break;
                }
            }
        }
    }
}

// User data is the target's index into state.targets — set at creation
// time (get_layer_surface / surface.frame calls below), so every event can
// go straight to the right OutputTarget without searching.

impl Dispatch<zwlr_layer_surface_v1::ZwlrLayerSurfaceV1, usize> for State {
    fn event(
        state: &mut Self,
        proxy: &zwlr_layer_surface_v1::ZwlrLayerSurfaceV1,
        event: zwlr_layer_surface_v1::Event,
        idx: &usize,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        let t = &mut state.targets[*idx];
        match event {
            zwlr_layer_surface_v1::Event::Configure { serial, width, height } => {
                proxy.ack_configure(serial);
                t.width = width as i32;
                t.height = height as i32;
                t.configured = true;
                t.need_redraw = true;
            }
            zwlr_layer_surface_v1::Event::Closed => {
                t.closed = true;
            }
            _ => {}
        }
    }
}

impl Dispatch<wl_callback::WlCallback, usize> for State {
    fn event(
        state: &mut Self,
        _: &wl_callback::WlCallback,
        event: wl_callback::Event,
        idx: &usize,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if let wl_callback::Event::Done { .. } = event {
            state.targets[*idx].need_redraw = true;
        }
    }
}

wayland_client::delegate_noop!(State: ignore wl_compositor::WlCompositor);
wayland_client::delegate_noop!(State: ignore wl_surface::WlSurface);
wayland_client::delegate_noop!(State: ignore zwlr_layer_shell_v1::ZwlrLayerShellV1);

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!(
            "usage: {} <video-path> <output-name> [output-name ...]",
            args.first().map(String::as_str).unwrap_or("waltzer-white")
        );
        return ExitCode::FAILURE;
    }
    let video_path = args[1].clone();
    let output_names: Vec<String> = args[2..].to_vec();
    if !Path::new(&video_path).exists() {
        eprintln!("waltzer-white: file not found: {video_path}");
        return ExitCode::FAILURE;
    }

    let conn = match Connection::connect_to_env() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("waltzer-white: couldn't connect to Wayland display: {e}");
            return ExitCode::FAILURE;
        }
    };
    let mut event_queue = conn.new_event_queue::<State>();
    let qh = event_queue.handle();
    let display = conn.display();
    let _registry = display.get_registry(&qh, ());

    let mut state = State {
        compositor: None,
        layer_shell: None,
        targets: output_names.into_iter().map(OutputTarget::new).collect(),
    };

    // Two roundtrips: one to receive the registry's globals and every
    // output's name event, a second in case any of that binding queued
    // further events (some compositors emit output info across a couple
    // of round trips).
    if let Err(e) = event_queue.roundtrip(&mut state) {
        eprintln!("waltzer-white: initial roundtrip failed: {e}");
        return ExitCode::FAILURE;
    }
    if let Err(e) = event_queue.roundtrip(&mut state) {
        eprintln!("waltzer-white: initial roundtrip failed: {e}");
        return ExitCode::FAILURE;
    }

    let compositor = match &state.compositor {
        Some(c) => c.clone(),
        None => {
            eprintln!("waltzer-white: compositor has no wl_compositor");
            return ExitCode::FAILURE;
        }
    };
    let layer_shell = match &state.layer_shell {
        Some(l) => l.clone(),
        None => {
            eprintln!("waltzer-white: compositor doesn't support wlr-layer-shell");
            return ExitCode::FAILURE;
        }
    };

    for i in 0..state.targets.len() {
        if state.targets[i].output.is_none() {
            eprintln!("waltzer-white: no output named {:?} found", state.targets[i].name);
            return ExitCode::FAILURE;
        }
        let target_output = state.targets[i].output.clone().unwrap();
        let surface = compositor.create_surface(&qh, ());
        let layer_surface = layer_shell.get_layer_surface(
            &surface,
            Some(&target_output),
            zwlr_layer_shell_v1::Layer::Background,
            "waltzer-white".to_string(),
            &qh,
            i,
        );
        layer_surface.set_anchor(
            zwlr_layer_surface_v1::Anchor::Top
                | zwlr_layer_surface_v1::Anchor::Bottom
                | zwlr_layer_surface_v1::Anchor::Left
                | zwlr_layer_surface_v1::Anchor::Right,
        );
        layer_surface.set_exclusive_zone(-1);
        layer_surface.set_keyboard_interactivity(zwlr_layer_surface_v1::KeyboardInteractivity::None);
        state.targets[i].layer_surface = Some(layer_surface);
        surface.commit();
        state.targets[i].wl_surface = Some(surface);
    }

    // Wait for every target to either configure or get closed.
    while state.targets.iter().any(|t| !t.configured && !t.closed) {
        if let Err(e) = event_queue.blocking_dispatch(&mut state) {
            eprintln!("waltzer-white: dispatch failed while waiting for configure: {e}");
            return ExitCode::FAILURE;
        }
    }
    for t in state.targets.iter().filter(|t| t.closed && !t.configured) {
        eprintln!("waltzer-white: output {:?} closed before it configured, skipping", t.name);
    }
    if !state.targets.iter().any(|t| t.configured) {
        eprintln!("waltzer-white: no output configured, nothing to render");
        return ExitCode::FAILURE;
    }

    // --- EGL setup (shared across every output) -------------------------
    let lib = match unsafe { libloading::Library::new("libEGL.so.1") } {
        Ok(l) => l,
        Err(e) => {
            eprintln!("waltzer-white: couldn't load libEGL.so.1: {e}");
            return ExitCode::FAILURE;
        }
    };
    let egl = match unsafe { khronos_egl::DynamicInstance::<khronos_egl::EGL1_4>::load_required_from(lib) } {
        Ok(e) => Rc::new(e),
        Err(e) => {
            eprintln!("waltzer-white: couldn't load EGL 1.4: {e}");
            return ExitCode::FAILURE;
        }
    };

    let display_ptr = display.id().as_ptr() as *mut c_void;
    let egl_display = match unsafe { egl.get_display(display_ptr) } {
        Some(d) => d,
        None => {
            eprintln!("waltzer-white: eglGetDisplay failed");
            return ExitCode::FAILURE;
        }
    };
    if let Err(e) = egl.initialize(egl_display) {
        eprintln!("waltzer-white: eglInitialize failed: {e}");
        return ExitCode::FAILURE;
    }
    if let Err(e) = egl.bind_api(khronos_egl::OPENGL_API) {
        eprintln!("waltzer-white: eglBindAPI(OPENGL) failed: {e}");
        return ExitCode::FAILURE;
    }

    let config_attribs = [
        khronos_egl::RED_SIZE, 8,
        khronos_egl::GREEN_SIZE, 8,
        khronos_egl::BLUE_SIZE, 8,
        khronos_egl::RENDERABLE_TYPE, khronos_egl::OPENGL_BIT,
        khronos_egl::SURFACE_TYPE, khronos_egl::WINDOW_BIT,
        khronos_egl::NONE,
    ];
    let egl_config = match egl.choose_first_config(egl_display, &config_attribs) {
        Ok(Some(c)) => c,
        _ => {
            eprintln!("waltzer-white: no matching EGL config");
            return ExitCode::FAILURE;
        }
    };

    // One EGL window + surface per configured output.
    for t in state.targets.iter_mut().filter(|t| t.configured) {
        let surface = t.wl_surface.as_ref().unwrap();
        let egl_window = match wayland_egl::WlEglSurface::new(surface.id(), t.width, t.height) {
            Ok(w) => w,
            Err(e) => {
                eprintln!("waltzer-white: wl_egl_window creation failed for {:?}: {e:?}", t.name);
                continue;
            }
        };
        let egl_surface = match unsafe {
            egl.create_window_surface(egl_display, egl_config, egl_window.ptr() as *mut c_void, None)
        } {
            Ok(s) => s,
            Err(e) => {
                eprintln!("waltzer-white: eglCreateWindowSurface failed for {:?}: {e}", t.name);
                continue;
            }
        };
        t._egl_window = Some(egl_window);
        t.egl_surface = Some(egl_surface);
    }
    if !state.targets.iter().any(|t| t.egl_surface.is_some()) {
        eprintln!("waltzer-white: no EGL surface could be created for any output");
        return ExitCode::FAILURE;
    }

    // One EGL context, reused sequentially across every output's surface —
    // contexts can be current against different surfaces at different
    // times, just not simultaneously from different threads, which never
    // happens here (everything is single-threaded).
    let context_attribs = [khronos_egl::NONE]; // no CONTEXT_CLIENT_VERSION: that's an ES-only hint, meaningless here
    let egl_context = match egl.create_context(egl_display, egl_config, None, &context_attribs) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("waltzer-white: eglCreateContext failed: {e}");
            return ExitCode::FAILURE;
        }
    };
    let first_surface = state.targets.iter().find_map(|t| t.egl_surface).unwrap();
    if let Err(e) = egl.make_current(egl_display, Some(first_surface), Some(first_surface), Some(egl_context)) {
        eprintln!("waltzer-white: eglMakeCurrent failed: {e}");
        return ExitCode::FAILURE;
    }

    // --- mpv setup (one shared decode) ------------------------------------
    let mpv = match Mpv::with_initializer(|init| {
        init.set_option("hwdec", "auto")?;
        init.set_option("loop-file", "inf")?;
        init.set_option("aid", "no")?; // fully disable audio, not just mute
        init.set_option("vo", "libmpv")?;
        // Multi-threaded software decode allocates per-thread frame buffers —
        // measured ~100MB (~30%) higher RSS on a 1080p clip than single-
        // threaded, for no benefit here: a looping background video has no
        // real-time deadline pressure, and CPU headroom is not the
        // bottleneck (only reachable when hwdec falls back to software
        // decode in the first place, same as this box does today).
        init.set_option("vd-lavc-threads", "1")?;
        Ok(())
    }) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("waltzer-white: mpv init failed: {e}");
            return ExitCode::FAILURE;
        }
    };
    struct GlCtx {
        egl: Rc<khronos_egl::DynamicInstance<khronos_egl::EGL1_4>>,
    }
    fn get_proc_address(ctx: &GlCtx, name: &str) -> *mut c_void {
        ctx.egl
            .get_proc_address(name)
            .map(|f| f as *mut c_void)
            .unwrap_or(std::ptr::null_mut())
    }

    let render_ctx = match mpv.create_render_context([
        RenderParam::ApiType(RenderParamApiType::OpenGl),
        RenderParam::InitParams(OpenGLInitParams { get_proc_address, ctx: GlCtx { egl: Rc::clone(&egl) } }),
    ]) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("waltzer-white: mpv render context creation failed: {e}");
            return ExitCode::FAILURE;
        }
    };

    // loadfile only after the render context exists: the "libmpv" VO has
    // nothing to attach to otherwise, and mpv fails the file with
    // MPV_ERROR_NOTHING_TO_PLAY instead of actually starting playback.
    if let Err(e) = mpv.command("loadfile", &[&video_path]) {
        eprintln!("waltzer-white: loadfile failed: {e}");
        return ExitCode::FAILURE;
    }

    // --- main loop --------------------------------------------------------
    // The frame callback must be requested *before* swap_buffers: Wayland
    // batches the frame() request into the same commit that swap_buffers
    // triggers implicitly. Requesting it after means the request rides on
    // nothing until the *next* commit, which never comes — so the very
    // first frame renders and every frame after it silently never fires.
    //
    // render() redraws the same already-decoded frame if none new is ready
    // (per libmpv2's own doc comment on RenderContext::render), so calling
    // it once per output per tick against one shared decode is safe — it
    // does not re-advance playback each time.
    loop {
        if state.targets.iter().all(|t| t.closed) {
            break;
        }
        for i in 0..state.targets.len() {
            let (configured, closed, need_redraw, width, height) = {
                let t = &state.targets[i];
                (t.configured, t.closed, t.need_redraw, t.width, t.height)
            };
            if !configured || closed || !need_redraw {
                continue;
            }
            let egl_surface = match state.targets[i].egl_surface {
                Some(s) => s,
                None => continue,
            };
            state.targets[i].need_redraw = false;
            state.targets[i].wl_surface.as_ref().unwrap().frame(&qh, i);
            if let Err(e) = egl.make_current(egl_display, Some(egl_surface), Some(egl_surface), Some(egl_context)) {
                eprintln!("waltzer-white: eglMakeCurrent failed for {:?}: {e}", state.targets[i].name);
                continue;
            }
            if let Err(e) = render_ctx.render::<GlCtx>(0, width, height, true) {
                eprintln!("waltzer-white: render failed for {:?}: {e}", state.targets[i].name);
                continue;
            }
            let _ = egl.swap_buffers(egl_display, egl_surface);
        }
        if let Err(e) = event_queue.blocking_dispatch(&mut state) {
            eprintln!("waltzer-white: dispatch failed: {e}");
            break;
        }
    }

    ExitCode::SUCCESS
}
