//! 后台运行时：窗口跟随线程 / 实时点线程 / 骨骼帧线程。
//! 全部通过 Tauri 事件把结果推给前端叠加层。

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

use crate::engine::project_from_raw;
use crate::model::WorldCoord;
use crate::state::AppState;
use crate::win32;

#[derive(Serialize, Clone)]
pub struct AlignPayload {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}

#[derive(Serialize, Clone)]
pub struct PointPayload {
    pub visible: bool,
    pub x: f64,
    pub y: f64,
    pub borderline: bool,
    pub reason: String,
}

#[derive(Serialize, Clone)]
pub struct BoneFrame {
    pub points: Vec<BonePoint>,
    pub connections: Vec<[usize; 2]>,
    /// 只显示这些序号的文本；为空表示全部。
    pub label_only: Vec<usize>,
    pub show_labels: bool,
    pub show_lines: bool,
    pub show_joints: bool,
    /// `label` = 以「显示序号」为准；`links` = 以「连接关系」为准。
    pub point_mode: String,
    pub font_size: f64,
    pub font_color: String,
    pub line_color: String,
    pub line_width: f64,
    pub point_radius: f64,
    pub point_outline_width: f64,
    pub point_color: String,
    pub visible_count: usize,
}

#[derive(Serialize, Clone)]
pub struct BonePoint {
    pub index: usize,
    pub x: f64,
    pub y: f64,
}

/// 窗口跟随线程：维护客户区位置/尺寸并控制叠加层可见性。
pub fn start_monitor(app: AppHandle, state: Arc<AppState>) {
    std::thread::spawn(move || {
        let mut last_geom: Option<(i32, i32, i32, i32)> = None;
        let mut last_visible: Option<bool> = None;
        loop {
            let follow = state.frame.lock().unwrap().follow_ms.max(4);
            std::thread::sleep(Duration::from_millis(follow));
            let hwnd = *state.hwnd.lock().unwrap();
            let overlay = match app.get_webview_window("overlay") {
                Some(w) => w,
                None => continue,
            };

            let mut visible = false;
            if let Some(h) = hwnd {
                let raw_hwnd = h as _;
                if win32::is_window_visible(raw_hwnd) {
                    if let Some((x, y, w, hh)) = win32::get_client_rect_on_screen(raw_hwnd) {
                        *state.client_offset.lock().unwrap() = (x, y);
                        *state.client_size.lock().unwrap() = (w, hh);
                        let (ew, eh) = state.effective_size();
                        let geom = (x, y, ew, eh);
                        if last_geom != Some(geom) {
                            let _ = overlay.set_position(tauri::PhysicalPosition::new(x, y));
                            let _ = overlay.set_size(tauri::PhysicalSize::new(
                                ew.max(1) as u32,
                                eh.max(1) as u32,
                            ));
                            last_geom = Some(geom);
                            let _ = app.emit(
                                "overlay:align",
                                AlignPayload {
                                    x,
                                    y,
                                    w: ew,
                                    h: eh,
                                },
                            );
                        }
                        visible = true;
                    }
                }
            }

            if last_visible != Some(visible) {
                if visible {
                    let _ = overlay.show();
                    if let Ok(h) = overlay.hwnd() {
                        win32::set_click_through(h.0 as _, true);
                        win32::make_topmost(h.0 as _);
                    }
                } else {
                    let _ = overlay.hide();
                    let _ = app.emit(
                        "realtime:point",
                        PointPayload {
                            visible: false,
                            x: 0.0,
                            y: 0.0,
                            borderline: false,
                            reason: String::new(),
                        },
                    );
                    let _ = app.emit("bone:frame", BoneFrame {
                        points: vec![],
                        connections: vec![],
                        label_only: vec![],
                        show_labels: true,
                        show_lines: true,
                        show_joints: true,
                        point_mode: "label".to_string(),
                        font_size: 13.0,
                        font_color: "#FFD54A".to_string(),
                        line_color: "#35E0FF".to_string(),
                        line_width: 1.6,
                        point_radius: 3.2,
                        point_outline_width: 1.6,
                        point_color: "#35E0FF".to_string(),
                        visible_count: 0,
                    });
                }
                last_visible = Some(visible);
            }
        }
    });
}

/// 实时点线程：以界面填写的世界坐标为输入，持续读取选中方案的矩阵并投影。
/// 矩阵存在内存里、随镜头变化，所以镜头移动时点会跟着走，
/// 可用来确认「镜头 / 物品世界坐标 / 矩阵」是否对得上。
pub fn start_realtime(app: AppHandle, state: Arc<AppState>) {
    std::thread::spawn(move || {
        // 叠加层当前是否显示着实时点：只在「有 → 无」时补发一次隐藏，避免残影和无效 IPC。
        let mut point_on = false;
        loop {
            let running = state.realtime.lock().unwrap().running;
            let scheme = state.filter.lock().unwrap().selected_scheme();
            let scheme = match scheme {
                Some(s) if running => s,
                _ => {
                    // 关闭实时 / 未选中方案：清掉叠加层上残留的点。
                    if point_on {
                        let _ = app.emit(
                            "realtime:point",
                            PointPayload {
                                visible: false,
                                x: 0.0,
                                y: 0.0,
                                borderline: false,
                                reason: String::new(),
                            },
                        );
                        point_on = false;
                    }
                    std::thread::sleep(Duration::from_millis(60));
                    continue;
                }
            };
            let (sw, sh) = state.effective_size();
            if sw <= 0 || sh <= 0 {
                std::thread::sleep(Duration::from_millis(30));
                continue;
            }
            // 用界面填写的世界坐标，而不是鼠标位置。
            let world = *state.world.lock().unwrap();

            match state.read_elements(scheme.address, scheme.data_type) {
                Ok(raw) => match project_from_raw(&scheme, &raw, world, sw, sh) {
                    Ok(p) => {
                        *state.last_failure.lock().unwrap() = None;
                        point_on = p.visible;
                        let _ = app.emit(
                            "realtime:point",
                            PointPayload {
                                visible: p.visible,
                                x: p.screen_x,
                                y: p.screen_y,
                                borderline: p.borderline,
                                reason: p.reason,
                            },
                        );
                    }
                    Err(e) => {
                        point_on = false;
                        let _ = app.emit(
                            "realtime:point",
                            PointPayload {
                                visible: false,
                                x: 0.0,
                                y: 0.0,
                                borderline: false,
                                reason: e.message(),
                            },
                        );
                    }
                },
                Err(e) => {
                    let msg = e.message();
                    let mut slot = state.last_failure.lock().unwrap();
                    if slot.as_deref() != Some(msg.as_str()) {
                        *slot = Some(msg);
                    }
                }
            }
            let rt_ms = state.frame.lock().unwrap().realtime_ms.max(8);
            std::thread::sleep(Duration::from_millis(rt_ms));
        }
    });
}

/// 骨骼帧线程：读取 count 个 Vec3 并用选中方案投影。
pub fn start_bone(app: AppHandle, state: Arc<AppState>) {
    std::thread::spawn(move || {
        // 叠加层当前是否显示着骨骼；关闭时补发一次空帧，清掉屏幕上的残留绘制。
        let mut frame_on = false;
        loop {
            let cfg = state.bone.lock().unwrap().clone();
            if !cfg.enabled || cfg.count == 0 {
                if frame_on {
                    let _ = app.emit(
                        "bone:frame",
                        BoneFrame {
                            points: vec![],
                            connections: vec![],
                            label_only: cfg.hidden.clone(),
                            show_labels: cfg.show_labels,
                            show_lines: cfg.show_lines,
                            show_joints: cfg.show_joints,
                            point_mode: cfg.point_mode.clone(),
                            font_size: cfg.font_size,
                            font_color: cfg.font_color.clone(),
                            line_color: cfg.line_color.clone(),
                            line_width: cfg.line_width,
                            point_radius: cfg.point_radius,
                            point_outline_width: cfg.point_outline_width,
                            point_color: cfg.point_color.clone(),
                            visible_count: 0,
                        },
                    );
                    frame_on = false;
                }
                std::thread::sleep(Duration::from_millis(80));
                continue;
            }
            let scheme = state.filter.lock().unwrap().selected_scheme();
            let scheme = match scheme {
                Some(s) => s,
                None => {
                    // 强制要求：必须先选中一条方案，否则不读、不画，并清掉残留绘制。
                    if frame_on {
                        let _ = app.emit(
                            "bone:frame",
                            BoneFrame {
                                points: vec![],
                                connections: vec![],
                                label_only: cfg.hidden.clone(),
                                show_labels: cfg.show_labels,
                                show_lines: cfg.show_lines,
                                show_joints: cfg.show_joints,
                                point_mode: cfg.point_mode.clone(),
                                font_size: cfg.font_size,
                                font_color: cfg.font_color.clone(),
                                line_color: cfg.line_color.clone(),
                                line_width: cfg.line_width,
                                point_radius: cfg.point_radius,
                                point_outline_width: cfg.point_outline_width,
                                point_color: cfg.point_color.clone(),
                                visible_count: 0,
                            },
                        );
                        frame_on = false;
                    }
                    std::thread::sleep(Duration::from_millis(80));
                    continue;
                }
            };
            let (sw, sh) = state.effective_size();
            // 矩阵地址直接取自选中方案（骨骼面板不再支持自定义地址）。
            let mat_raw = match state.read_elements(scheme.address, scheme.data_type) {
                Ok(r) => r,
                Err(_) => {
                    std::thread::sleep(Duration::from_millis(100));
                    continue;
                }
            };
            let matrix = scheme.build_matrix(&mat_raw);

            let mut points: Vec<BonePoint> = Vec::new();
            for i in 0..cfg.count {
                // 「显示序号」只影响序号文本，不影响点本身：所有点照常读取、投影与连线。
                let addr = cfg.base_address.wrapping_add((i * cfg.stride) as u64);
                let raw3 = match state.read_elements(addr, cfg.data_type) {
                    Ok(r) => r,
                    Err(_) => continue,
                };
                if raw3.len() < 3 {
                    continue;
                }
                let world = WorldCoord {
                    x: raw3[0],
                    y: raw3[1],
                    z: raw3[2],
                };
                if let Some(m) = &matrix {
                    let p = crate::engine::project_with_matrix(
                        m,
                        scheme.mul_direction,
                        scheme.clip_w_sign,
                        world,
                        sw,
                        sh,
                    );
                    if p.visible {
                        points.push(BonePoint {
                            index: i,
                            x: p.screen_x,
                            y: p.screen_y,
                        });
                    }
                }
            }
            let connections: Vec<[usize; 2]> =
                cfg.connections.iter().map(|(a, b)| [*a, *b]).collect();
            let _ = app.emit(
                "bone:frame",
                BoneFrame {
                    visible_count: points.len(),
                    points,
                    connections,
                    label_only: cfg.hidden.clone(),
                    show_labels: cfg.show_labels,
                    show_lines: cfg.show_lines,
                    show_joints: cfg.show_joints,
                    point_mode: cfg.point_mode.clone(),
                    font_size: cfg.font_size,
                    font_color: cfg.font_color.clone(),
                    line_color: cfg.line_color.clone(),
                    line_width: cfg.line_width,
                    point_radius: cfg.point_radius,
                    point_outline_width: cfg.point_outline_width,
                    point_color: cfg.point_color.clone(),
                },
            );
            frame_on = true;
            let bone_ms = state.frame.lock().unwrap().bone_ms.max(10);
            std::thread::sleep(Duration::from_millis(bone_ms));
        }
    });
}

// ----------------------------------------------------------------------
// 拖拽选取目标窗口
// ----------------------------------------------------------------------

static PICKING: AtomicBool = AtomicBool::new(false);

#[derive(Serialize, Clone)]
pub struct PickHover {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
    pub pid: u32,
    pub name: String,
    pub title: String,
}

#[derive(Serialize, Clone)]
pub struct PickDone {
    pub ok: bool,
    pub pid: u32,
    pub name: String,
    pub title: String,
    pub reason: String,
}

pub fn is_picking() -> bool {
    PICKING.load(Ordering::SeqCst)
}

/// 进入拖拽选取模式：
/// 1. 显示全屏选取层（透明、点击穿透、置顶）
/// 2. 以 ~60Hz 轮询鼠标下的顶层窗口，把矩形推给前端画轮廓
/// 3. 左键松开时结束，把结果推给主窗口
///
/// 之所以轮询而不是监听窗口消息：主窗口此时已隐藏，前端拿不到全局鼠标事件。
pub fn start_pick(app: AppHandle) {
    if PICKING.swap(true, Ordering::SeqCst) {
        return;
    }
    std::thread::spawn(move || {
        let self_pid = std::process::id();

        if let Some(picker) = app.get_webview_window("picker") {
            let (sw, sh) = win32::primary_screen_size();
            let _ = picker.set_position(tauri::PhysicalPosition::new(0, 0));
            let _ = picker.set_size(tauri::PhysicalSize::new(sw.max(1) as u32, sh.max(1) as u32));
            let _ = picker.show();
            if let Ok(h) = picker.hwnd() {
                win32::set_click_through(h.0 as _, true);
                win32::make_topmost(h.0 as _);
            }
        }

        // 留一点时间给选取层渲染首帧
        std::thread::sleep(Duration::from_millis(110));

        let mut last: Option<(i32, i32, i32, i32)> = None;
        let mut hover_pid: u32 = 0;
        let mut hover_name = String::new();
        let mut hover_title = String::new();
        let mut got = false;

        loop {
            std::thread::sleep(Duration::from_millis(16));

            let (cx, cy) = win32::get_cursor_pos();
            if let Some(h) = win32::window_from_point(cx, cy) {
                let root = win32::root_window(h);
                let pid = win32::window_pid(root);
                if pid != 0 && pid != self_pid {
                    if let Some((x, y, w, hh)) = win32::get_window_rect(root) {
                        hover_pid = pid;
                        hover_name = win32::process_name(pid);
                        hover_title = win32::window_title(root);
                        got = true;
                        if last != Some((x, y, w, hh)) {
                            last = Some((x, y, w, hh));
                            let _ = app.emit(
                                "pick:hover",
                                PickHover {
                                    x,
                                    y,
                                    w,
                                    h: hh,
                                    pid,
                                    name: hover_name.clone(),
                                    title: hover_title.clone(),
                                },
                            );
                        }
                    }
                }
            }

            if !win32::is_lbutton_down() {
                break;
            }
        }

        if let Some(picker) = app.get_webview_window("picker") {
            let _ = picker.hide();
        }

        let _ = app.emit(
            "pick:done",
            PickDone {
                ok: got,
                pid: hover_pid,
                name: hover_name,
                title: hover_title,
                reason: if got {
                    String::new()
                } else {
                    "没有选中任何窗口".to_string()
                },
            },
        );

        PICKING.store(false, Ordering::SeqCst);
    });
}
