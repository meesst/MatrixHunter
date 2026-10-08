//! Tauri 命令（前端唯一入口）。
//! 对应原 ui/main_window.py 的各按钮/输入回调。

use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

use crate::engine::{MatrixGenerator, SchemeState};
use crate::errors::{ErrorPayload, MhError, MhResult};
use crate::model::*;
use crate::state::AppState;
use crate::win32;

/// 单次枚举的候选地址上限。每个地址展开为 8 个方案，故 1 万地址 ≈ 8 万方案。
const MAX_ADDRESSES: usize = 10_000;

#[derive(Serialize, Clone)]
pub struct SchemeView {
    pub scheme_id: String,
    pub address: u64,
    pub address_hex: String,
    pub description: String,
    pub data_type: String,
    pub shape: String,
    pub layout: String,
    pub mul_direction: String,
    pub clip_w_sign: String,
    pub status: String,
}

fn view(s: &MatrixScheme, st: SchemeState) -> SchemeView {
    SchemeView {
        scheme_id: s.scheme_id.clone(),
        address: s.address,
        address_hex: format!("0x{:X}", s.address),
        description: s.description(),
        data_type: s.data_type.as_str().to_string(),
        shape: s.shape.as_str().to_string(),
        layout: s.layout.as_str().to_string(),
        mul_direction: s.mul_direction.as_str().to_string(),
        clip_w_sign: s.clip_w_sign.as_str().to_string(),
        status: match st {
            SchemeState::Active => "active".to_string(),
            SchemeState::Eliminated => "eliminated".to_string(),
        },
    }
}

#[derive(Serialize, Clone)]
pub struct AttachInfo {
    pub pid: u32,
    pub name: String,
    pub hwnd_found: bool,
    pub client_x: i32,
    pub client_y: i32,
    pub client_w: i32,
    pub client_h: i32,
}

#[derive(Serialize, Clone)]
pub struct EnumerateResult {
    pub schemes: Vec<SchemeView>,
    pub invalid: Vec<String>,
    pub total: usize,
}

#[derive(Serialize, Clone)]
pub struct PreviewResult {
    pub visible: bool,
    pub x: f64,
    pub y: f64,
    pub reason: String,
    pub borderline: bool,
}

#[derive(Serialize, Clone)]
pub struct PoolSummary {
    pub total: usize,
    pub active: usize,
    pub eliminated: usize,
    pub selected: Option<String>,
    pub can_undo: bool,
    pub undo_depth: usize,
}

// ----------------------------------------------------------------------
// 进程 / 附加
// ----------------------------------------------------------------------

#[tauri::command]
pub fn list_processes() -> Result<Vec<win32::ProcessInfo>, ErrorPayload> {
    win32::list_processes().map_err(Into::into)
}

fn find_process_name(pid: u32) -> String {
    win32::list_processes()
        .ok()
        .and_then(|list| list.into_iter().find(|p| p.pid == pid))
        .map(|p| p.name)
        .unwrap_or_else(|| format!("pid {pid}"))
}

fn do_attach(state: &Arc<AppState>, pid: u32) -> MhResult<AttachInfo> {
    let handle = Arc::new(win32::ProcessHandle::attach(pid)?);
    let hwnd = win32::find_main_window(pid);
    let mut info = AttachInfo {
        pid,
        name: find_process_name(pid),
        hwnd_found: hwnd.is_some(),
        client_x: 0,
        client_y: 0,
        client_w: 0,
        client_h: 0,
    };
    if let Some(h) = hwnd {
        if let Some((x, y, w, hh)) = win32::get_client_rect_on_screen(h) {
            info.client_x = x;
            info.client_y = y;
            info.client_w = w;
            info.client_h = hh;
        }
    }
    *state.process.lock().unwrap() = Some(handle);
    *state.pid.lock().unwrap() = Some(pid);
    *state.hwnd.lock().unwrap() = hwnd.map(|h| h as isize);
    *state.client_offset.lock().unwrap() = (info.client_x, info.client_y);
    *state.client_size.lock().unwrap() = (info.client_w, info.client_h);
    *state.size_override.lock().unwrap() = None;
    state.filter.lock().unwrap().clear();
    let mut rt = state.realtime.lock().unwrap();
    rt.running = false;
    rt.failure = None;
    state.bone.lock().unwrap().enabled = false;
    Ok(info)
}

#[tauri::command]
pub fn attach_process(state: State<'_, Arc<AppState>>, pid: u32) -> Result<AttachInfo, ErrorPayload> {
    do_attach(&state, pid).map_err(Into::into)
}

#[tauri::command]
pub fn detach_process(state: State<'_, Arc<AppState>>) -> Result<(), ErrorPayload> {
    *state.process.lock().unwrap() = None;
    *state.pid.lock().unwrap() = None;
    *state.hwnd.lock().unwrap() = None;
    *state.size_override.lock().unwrap() = None;
    state.filter.lock().unwrap().clear();
    state.realtime.lock().unwrap().running = false;
    state.bone.lock().unwrap().enabled = false;
    Ok(())
}

#[derive(Serialize, Clone)]
pub struct WindowUnderCursor {
    pub pid: u32,
    pub name: String,
    pub title: String,
    pub class_name: String,
    pub hwnd_found: bool,
}

/// 进入拖拽选取模式（主窗口需由前端先行隐藏）。
#[tauri::command]
pub fn start_pick(app: AppHandle) -> Result<(), ErrorPayload> {
    crate::runtime::start_pick(app);
    Ok(())
}

/// 读取当前鼠标位置下的窗口（配合热键选择）。
#[tauri::command]
pub fn window_under_cursor() -> Result<WindowUnderCursor, ErrorPayload> {
    let (x, y) = win32::get_cursor_pos();
    let hwnd = win32::window_from_point(x, y)
        .ok_or_else(|| MhError::Window("光标下没有窗口".to_string()))?;
    let pid = win32::window_pid(hwnd);
    let name = find_process_name(pid);
    let main = win32::find_main_window(pid);
    Ok(WindowUnderCursor {
        pid,
        name,
        title: win32::window_title(hwnd),
        class_name: win32::window_class(hwnd),
        hwnd_found: main.is_some(),
    })
}

#[tauri::command]
pub fn refresh_target_window(state: State<'_, Arc<AppState>>) -> Result<Option<AttachInfo>, ErrorPayload> {
    let pid = *state.pid.lock().unwrap();
    let pid = match pid {
        Some(p) => p,
        None => return Ok(None),
    };
    let hwnd = win32::find_main_window(pid);
    let mut info = AttachInfo {
        pid,
        name: find_process_name(pid),
        hwnd_found: hwnd.is_some(),
        client_x: 0,
        client_y: 0,
        client_w: 0,
        client_h: 0,
    };
    if let Some(h) = hwnd {
        if let Some((x, y, w, hh)) = win32::get_client_rect_on_screen(h) {
            info.client_x = x;
            info.client_y = y;
            info.client_w = w;
            info.client_h = hh;
        }
    }
    *state.hwnd.lock().unwrap() = hwnd.map(|h| h as isize);
    *state.client_offset.lock().unwrap() = (info.client_x, info.client_y);
    *state.client_size.lock().unwrap() = (info.client_w, info.client_h);
    Ok(Some(info))
}

/// 当前附加目标的窗口详细信息（供「窗口信息」面板展示）。
#[tauri::command]
pub fn window_detail(
    state: State<'_, Arc<AppState>>,
) -> Result<Option<win32::WindowDetailInfo>, ErrorPayload> {
    let pid = *state.pid.lock().unwrap();
    let pid = match pid {
        Some(p) => p,
        None => return Ok(None),
    };
    match win32::find_main_window(pid) {
        Some(hwnd) => Ok(Some(win32::window_detail_info(pid, hwnd))),
        None => Ok(None),
    }
}

#[tauri::command]
pub fn set_size_override(
    state: State<'_, Arc<AppState>>,
    width: i32,
    height: i32,
) -> Result<(), ErrorPayload> {
    if width <= 0 || height <= 0 {
        *state.size_override.lock().unwrap() = None;
    } else {
        *state.size_override.lock().unwrap() = Some((width, height));
    }
    Ok(())
}

// ----------------------------------------------------------------------
// 枚举 / 过滤
// ----------------------------------------------------------------------

fn parse_hex(text: &str) -> Option<u64> {
    let t = text.trim();
    if t.is_empty() {
        return None;
    }
    let t = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")).unwrap_or(t);
    u64::from_str_radix(t, 16).ok()
}

/// 解析候选地址，支持两种写法：
///   1. 绝对十六进制地址：`0x7FF6A1B2C3D0` 或 `14C3D0A0`
///   2. 模块 + 偏移：`"DeadzoneSteam-Win64-Shipping.exe"+B699A54`
///      （引号可省略，模块名不限大小写、可省略扩展名）
/// 模块写法必须先附加进程，用于读取模块基址。
fn parse_target(text: &str, pid: Option<u32>) -> Result<u64, String> {
    let t = text.trim();
    if t.is_empty() {
        return Err("空地址".to_string());
    }

    // 模块 + 偏移：以最后一个 '+' 分隔（模块名/token 中不会出现 '+'）
    if let Some((module_part, offset_part)) = t.rsplit_once('+') {
        let module = module_part.trim().trim_matches('"').trim();
        if module.is_empty() {
            return Err(format!("模块名为空: {t}"));
        }
        let offset =
            parse_hex(offset_part).ok_or_else(|| format!("偏移非法: {}", offset_part.trim()))?;
        let pid = pid.ok_or_else(|| "未附加进程，无法解析模块基址".to_string())?;
        let base =
            win32::module_base(pid, module).ok_or_else(|| format!("未找到模块 {module}"))?;
        let addr = base.wrapping_add(offset);
        return if addr == 0 {
            Err(format!("解析结果为空地址: {t}"))
        } else {
            Ok(addr)
        };
    }

    match parse_hex(t) {
        Some(a) if a != 0 => Ok(a),
        _ => Err(format!("非法地址: {t}")),
    }
}

#[tauri::command]
pub fn enumerate(
    state: State<'_, Arc<AppState>>,
    addresses: Vec<String>,
    data_type: DataType,
) -> Result<EnumerateResult, ErrorPayload> {
    let mut invalid: Vec<String> = Vec::new();
    let mut addrs: Vec<u64> = Vec::new();
    let pid = *state.pid.lock().unwrap();
    let mut seen: std::collections::HashSet<u64> = std::collections::HashSet::new();
    for raw in addresses.iter() {
        match parse_target(raw, pid) {
            Ok(a) => {
                if seen.insert(a) {
                    addrs.push(a);
                }
            }
            Err(e) => invalid.push(format!("{raw} ({e})")),
        }
    }
    if addrs.is_empty() {
        return Err(MhError::InvalidAddress("没有合法地址".to_string()).into());
    }
    if addrs.len() > MAX_ADDRESSES {
        return Err(MhError::Enumeration(format!(
            "地址数量 {} 超过上限 {MAX_ADDRESSES}",
            addrs.len()
        ))
        .into());
    }
    addrs.sort_unstable();

    let mut schemes: Vec<MatrixScheme> = Vec::with_capacity(addrs.len() * 8);
    for a in &addrs {
        schemes.extend(MatrixGenerator::generate(*a, data_type));
    }
    let total = schemes.len();
    let views: Vec<SchemeView> = schemes.iter().map(|s| view(s, SchemeState::Active)).collect();
    state.filter.lock().unwrap().load(schemes);
    Ok(EnumerateResult {
        schemes: views,
        invalid,
        total,
    })
}

#[tauri::command]
pub fn filter(
    state: State<'_, Arc<AppState>>,
    quadrant: Quadrant,
    world: WorldCoord,
) -> Result<FilterOutcome, ErrorPayload> {
    let (sw, sh) = state.effective_size();
    // 过滤用的世界坐标回写，供实时/预览复用，保证三者口径一致。
    *state.world.lock().unwrap() = world;
    let proc: Arc<AppState> = (*state).clone();
    let outcome = {
        let mut f = state.filter.lock().unwrap();
        f.apply(quadrant, world, sw, sh, |addr, dt| proc.read_elements(addr, dt))
    };
    Ok(outcome)
}

#[tauri::command]
pub fn bone_apply_filter(
    state: State<'_, Arc<AppState>>,
    quadrant: Quadrant,
) -> Result<FilterOutcome, ErrorPayload> {
    let bone = state.bone.lock().unwrap().clone();
    if bone.base_address == 0 {
        return Err(MhError::InvalidAddress("骨骼基址为空".to_string()).into());
    }
    // 用骨骼首点作为世界坐标输入。
    let p = state.read_elements(bone.base_address, bone.data_type)?;
    if p.len() < 3 {
        return Err(MhError::Enumeration("骨骼点数据不足".to_string()).into());
    }
    let world = WorldCoord {
        x: p[0],
        y: p[1],
        z: p[2],
    };
    let (sw, sh) = state.effective_size();
    // 骨骼过滤用的世界坐标同样回写，供实时/预览复用。
    *state.world.lock().unwrap() = world;
    let proc: Arc<AppState> = (*state).clone();
    let outcome = {
        let mut f = state.filter.lock().unwrap();
        f.apply(quadrant, world, sw, sh, |addr, dt| proc.read_elements(addr, dt))
    };
    Ok(outcome)
}

#[tauri::command]
pub fn undo_filter(state: State<'_, Arc<AppState>>) -> Result<Option<usize>, ErrorPayload> {
    Ok(state.filter.lock().unwrap().undo())
}

#[tauri::command]
pub fn reset_pool(state: State<'_, Arc<AppState>>) -> Result<(), ErrorPayload> {
    state.filter.lock().unwrap().clear();
    Ok(())
}

#[tauri::command]
pub fn remove_scheme(state: State<'_, Arc<AppState>>, scheme_id: String) -> Result<bool, ErrorPayload> {
    Ok(state.filter.lock().unwrap().remove(&scheme_id))
}

#[tauri::command]
pub fn select_scheme(
    state: State<'_, Arc<AppState>>,
    scheme_id: String,
) -> Result<bool, ErrorPayload> {
    Ok(state.filter.lock().unwrap().select(&scheme_id))
}

#[tauri::command]
pub fn get_pool_summary(state: State<'_, Arc<AppState>>) -> Result<PoolSummary, ErrorPayload> {
    let f = state.filter.lock().unwrap();
    let total = f.pool.len();
    let active = f.active_count();
    Ok(PoolSummary {
        total,
        active,
        eliminated: total - active,
        selected: f.selected_id.clone(),
        can_undo: !f.undo_stack.is_empty(),
        undo_depth: f.undo_stack.len(),
    })
}

#[tauri::command]
pub fn get_active_schemes(state: State<'_, Arc<AppState>>) -> Result<Vec<SchemeView>, ErrorPayload> {
    let f = state.filter.lock().unwrap();
    Ok(f.active_schemes()
        .iter()
        .map(|s| view(s, SchemeState::Active))
        .collect())
}

#[tauri::command]
pub fn get_all_schemes(state: State<'_, Arc<AppState>>) -> Result<Vec<SchemeView>, ErrorPayload> {
    let f = state.filter.lock().unwrap();
    Ok(f.pool.iter().map(|e| view(&e.scheme, e.state)).collect())
}

/// 用当前鼠标位置预览某个方案（发黄色点给叠加层）。
#[tauri::command]
pub fn preview_scheme(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    scheme_id: String,
) -> Result<PreviewResult, ErrorPayload> {
    let scheme = {
        let f = state.filter.lock().unwrap();
        f.pool
            .iter()
            .find(|e| e.scheme.scheme_id == scheme_id)
            .map(|e| e.scheme.clone())
    };
    let scheme = match scheme {
        Some(s) => s,
        None => {
            return Err(MhError::Other("方案不存在".to_string()).into());
        }
    };
    let (sw, sh) = state.effective_size();
    // 用界面填写的世界坐标，而不是鼠标位置。
    let world = *state.world.lock().unwrap();
    let raw = state.read_elements(scheme.address, scheme.data_type)?;
    let p = crate::engine::project_from_raw(&scheme, &raw, world, sw, sh)?;
    let _ = app.emit("overlay:preview", PreviewResult {
        visible: p.visible,
        x: p.screen_x,
        y: p.screen_y,
        reason: p.reason.clone(),
        borderline: p.borderline,
    });
    Ok(PreviewResult {
        visible: p.visible,
        x: p.screen_x,
        y: p.screen_y,
        reason: p.reason,
        borderline: p.borderline,
    })
}

#[tauri::command]
pub fn stop_preview(app: AppHandle) -> Result<(), ErrorPayload> {
    let _ = app.emit(
        "overlay:preview",
        PreviewResult {
            visible: false,
            x: 0.0,
            y: 0.0,
            reason: String::new(),
            borderline: false,
        },
    );
    Ok(())
}

// ----------------------------------------------------------------------
// 实时 / 骨骼 / 叠加层设置
// ----------------------------------------------------------------------

#[tauri::command]
pub fn start_realtime(state: State<'_, Arc<AppState>>) -> Result<(), ErrorPayload> {
    if !state.is_attached() {
        return Err(MhError::Attach("请先附加进程".to_string()).into());
    }
    state.realtime.lock().unwrap().running = true;
    Ok(())
}

#[tauri::command]
pub fn stop_realtime(state: State<'_, Arc<AppState>>) -> Result<(), ErrorPayload> {
    state.realtime.lock().unwrap().running = false;
    Ok(())
}

/// 同步界面填写的世界坐标（实时点与预览的投影输入）。
#[tauri::command]
pub fn set_world(
    state: State<'_, Arc<AppState>>,
    x: f64,
    y: f64,
    z: f64,
) -> Result<(), ErrorPayload> {
    *state.world.lock().unwrap() = WorldCoord { x, y, z };
    Ok(())
}

fn default_outline_width() -> f64 {
    1.6
}

fn default_true() -> bool {
    true
}

fn default_point_mode() -> String {
    "label".to_string()
}

#[derive(Deserialize)]
pub struct BoneConfigInput {
    pub base_address: String,
    pub count: usize,
    pub stride: usize,
    pub address: String,
    /// 只绘制这些序号的文本；为空表示全部。仅影响序号，不影响连线。
    #[serde(default)]
    pub hidden: Vec<usize>,
    #[serde(default)]
    pub connections: Vec<[usize; 2]>,
    #[serde(default = "default_true")]
    pub show_labels: bool,
    #[serde(default = "default_true")]
    pub show_lines: bool,
    #[serde(default = "default_true")]
    pub show_joints: bool,
    /// 点位筛选模式：label / links
    #[serde(default = "default_point_mode")]
    pub point_mode: String,
    pub font_size: f64,
    pub font_color: String,
    pub line_color: String,
    pub line_width: f64,
    pub point_radius: f64,
    /// 关节轮廓粗细（与连线粗细独立）。
    #[serde(default = "default_outline_width")]
    pub point_outline_width: f64,
    pub point_color: String,
    pub data_type: DataType,
    pub enabled: bool,
}

#[tauri::command]
pub fn set_bone_config(
    state: State<'_, Arc<AppState>>,
    config: BoneConfigInput,
) -> Result<(), ErrorPayload> {
    let pid = *state.pid.lock().unwrap();
    let base = parse_target(&config.base_address, pid).unwrap_or(0);
    let addr = parse_target(&config.address, pid).unwrap_or(0);
    let mut b = state.bone.lock().unwrap();
    b.base_address = base;
    b.count = config.count;
    b.stride = config.stride.max(1);
    b.address = addr;
    b.hidden = config.hidden;
    b.connections = config.connections.iter().map(|p| (p[0], p[1])).collect();
    b.show_labels = config.show_labels;
    b.show_lines = config.show_lines;
    b.show_joints = config.show_joints;
    b.point_mode = config.point_mode;
    b.font_size = config.font_size;
    b.font_color = config.font_color;
    b.line_color = config.line_color;
    b.line_width = config.line_width;
    b.point_radius = config.point_radius;
    b.point_outline_width = config.point_outline_width;
    b.point_color = config.point_color;
    b.data_type = config.data_type;
    b.enabled = config.enabled;
    Ok(())
}

/// 设置绘制 / 跟随频率（毫秒）。
#[tauri::command]
pub fn set_frame_config(
    state: State<'_, Arc<AppState>>,
    follow_ms: u64,
    realtime_ms: u64,
    bone_ms: u64,
) -> Result<(), ErrorPayload> {
    let mut f = state.frame.lock().unwrap();
    f.follow_ms = follow_ms.clamp(4, 500);
    f.realtime_ms = realtime_ms.clamp(8, 500);
    f.bone_ms = bone_ms.clamp(10, 1000);
    Ok(())
}

#[derive(Serialize, Clone)]
pub struct AppInfo {
    pub version: String,
    pub name: String,
}

/// 硬件 / 本进程性能快照（标题栏性能监测）。
#[tauri::command]
pub fn perf_snapshot() -> win32::PerfSnapshot {
    win32::perf_snapshot()
}

#[tauri::command]
pub fn app_info() -> AppInfo {
    AppInfo {
        name: "MatrixHunter".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    }
}

#[tauri::command]
pub fn read_address(
    state: State<'_, Arc<AppState>>,
    address: String,
    data_type: DataType,
) -> Result<Vec<f64>, ErrorPayload> {
    let pid = *state.pid.lock().unwrap();
    let addr = parse_target(&address, pid)
        .map_err(|e| MhError::InvalidAddress(format!("地址解析失败: {address} ({e})")))?;
    state.read_elements(addr, data_type).map_err(Into::into)
}

#[tauri::command]
pub fn save_settings(
    app: AppHandle,
    settings: crate::config::Settings,
) -> Result<(), ErrorPayload> {
    crate::config::save(&app, &settings).map_err(Into::into)
}

#[tauri::command]
pub fn load_settings(app: AppHandle) -> Result<crate::config::Settings, ErrorPayload> {
    Ok(crate::config::load(&app))
}
