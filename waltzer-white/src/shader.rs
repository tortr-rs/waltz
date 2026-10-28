//! Shader wallpapers: a fragment shader drawn over the whole output every
//! frame, no mpv involved. Shadertoy style, so shaders from there mostly
//! work as they are: the file defines
//!
//!     void mainImage(out vec4 fragColor, in vec2 fragCoord)
//!
//! and gets `iTime` (seconds, frozen while paused) and `iResolution`. A file
//! with its own `void main(` is used as it is.

use std::ffi::CString;
use std::time::{Duration, Instant};

const VERT: &str = "#version 130
void main() {
    // one triangle that covers the screen
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
";

const HEAD: &str = "#version 130
uniform vec3 iResolution;
uniform float iTime;
uniform int iFrame;
out vec4 waltz_color;
";

const FOOT: &str = "
void main() { mainImage(waltz_color, gl_FragCoord.xy); }
";

pub struct Shader {
    prog: u32,
    vao: u32,
    res: i32,
    time: i32,
    frame: i32,
    frames: i32,
    // playing time: what ran before the last pause, and since when it runs again
    played: Duration,
    since: Option<Instant>,
}

pub fn is_shader(path: &str) -> bool {
    let p = path.to_ascii_lowercase();
    p.ends_with(".frag") || p.ends_with(".glsl") || p.ends_with(".shader")
}

unsafe fn compile(kind: u32, src: &str) -> Result<u32, String> {
    let s = gl::CreateShader(kind);
    let c = CString::new(src).map_err(|e| e.to_string())?;
    gl::ShaderSource(s, 1, &c.as_ptr(), std::ptr::null());
    gl::CompileShader(s);
    let mut ok = 0;
    gl::GetShaderiv(s, gl::COMPILE_STATUS, &mut ok);
    if ok == 0 {
        let mut len = 0;
        gl::GetShaderiv(s, gl::INFO_LOG_LENGTH, &mut len);
        let mut log = vec![0u8; len.max(1) as usize];
        gl::GetShaderInfoLog(s, len, std::ptr::null_mut(), log.as_mut_ptr() as *mut _);
        return Err(String::from_utf8_lossy(&log).trim_end_matches('\0').to_string());
    }
    Ok(s)
}

impl Shader {
    /// Needs a current GL context with gl::load_with already done.
    pub fn new(src: &str) -> Result<Shader, String> {
        let frag = if src.contains("void main(") {
            src.to_string()
        } else {
            format!("{HEAD}{src}{FOOT}")
        };
        unsafe {
            let v = compile(gl::VERTEX_SHADER, VERT)?;
            let f = compile(gl::FRAGMENT_SHADER, &frag)?;
            let prog = gl::CreateProgram();
            gl::AttachShader(prog, v);
            gl::AttachShader(prog, f);
            gl::LinkProgram(prog);
            let mut ok = 0;
            gl::GetProgramiv(prog, gl::LINK_STATUS, &mut ok);
            if ok == 0 {
                return Err("the shader didn't link".into());
            }
            let mut vao = 0;
            gl::GenVertexArrays(1, &mut vao);
            let loc = |n: &str| gl::GetUniformLocation(prog, CString::new(n).unwrap().as_ptr());
            Ok(Shader {
                prog,
                vao,
                res: loc("iResolution"),
                time: loc("iTime"),
                frame: loc("iFrame"),
                frames: 0,
                played: Duration::ZERO,
                since: Some(Instant::now()),
            })
        }
    }

    pub fn set_paused(&mut self, paused: bool) {
        match (paused, self.since) {
            (true, Some(s)) => {
                self.played += s.elapsed();
                self.since = None;
            }
            (false, None) => self.since = Some(Instant::now()),
            _ => {}
        }
    }

    pub fn render(&mut self, width: i32, height: i32) {
        self.render_to(0, width, height);
    }

    pub fn render_to(&mut self, fbo: u32, width: i32, height: i32) {
        let t = self.played + self.since.map_or(Duration::ZERO, |s| s.elapsed());
        unsafe {
            gl::BindFramebuffer(gl::FRAMEBUFFER, fbo);
            gl::Viewport(0, 0, width, height);
            gl::UseProgram(self.prog);
            gl::Uniform3f(self.res, width as f32, height as f32, 1.0);
            gl::Uniform1f(self.time, t.as_secs_f32());
            gl::Uniform1i(self.frame, self.frames);
            gl::BindVertexArray(self.vao);
            gl::DrawArrays(gl::TRIANGLES, 0, 3);
        }
        self.frames += 1;
    }
}
