//! Win32 封装（对应原 core/process_manager.py + core/memory_reader.py + 窗口/DPI 工具）。
//!
//! 使用 `windows-sys` 原始 FFI，避免 `windows` crate 的版本/类型约束问题。

#![cfg(windows)]

use std::ffi::c_void;

use serde::Serialize;
use windows_sys::Win32::Foundation::{
    BOOL, CloseHandle, FILETIME, HANDLE, HWND, INVALID_HANDLE_VALUE, LPARAM, POINT, RECT,
};
use windows_sys::Win32::Graphics::Gdi::ClientToScreen;
use windows_sys::Win32::System::Diagnostics::Debug::ReadProcessMemory;
use windows_sys::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, PROCESSENTRY32W, Process32FirstW, Process32NextW,
    TH32CS_SNAPPROCESS,
};
use windows_sys::Win32::System::Threading::{
    IsWow64Process, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_VM_READ,
};
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetAncestor, GetClassNameW, GetClientRect, GetCursorPos, GetParent,
    GetWindowLongW, GetWindowRect, GetWindowTextW, GetWindowThreadProcessId, IsIconic, IsWindow,
    IsWindowVisible, SetWindowLongW, SetWindowPos, WindowFromPoint, GA_ROOT, GWL_EXSTYLE,
    GWL_STYLE, HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, WS_EX_LAYERED,
    WS_EX_TRANSPARENT,
};

use crate::errors::{MhError, MhResult};
use crate::model::DataType;

#[derive(Debug, Clone, Serialize)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
    pub is_64bit: bool,
}

// ----------------------------------------------------------------------
// 进程
// ----------------------------------------------------------------------

fn invalid_handle(h: HANDLE) -> bool {
    h.is_null() || h == INVALID_HANDLE_VALUE
}

/// 枚举进程。
pub fn list_processes() -> MhResult<Vec<ProcessInfo>> {
    let mut result: Vec<ProcessInfo> = Vec::new();
    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if invalid_handle(snapshot) {
            return Err(MhError::ProcessList(
                "CreateToolhelp32Snapshot 失败".to_string(),
            ));
        }
        let mut entry: PROCESSENTRY32W = std::mem::zeroed();
        entry.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
        if Process32FirstW(snapshot, &mut entry) != 0 {
            loop {
                let pid = entry.th32ProcessID;
                let name = wide_to_string(&entry.szExeFile);
                if pid != 0 && !name.is_empty() {
                    let is64 = is_process_64bit(pid);
                    result.push(ProcessInfo {
                        pid,
                        name,
                        is_64bit: is64,
                    });
                }
                if Process32NextW(snapshot, &mut entry) == 0 {
                    break;
                }
            }
        }
        let _ = CloseHandle(snapshot);
    }
    Ok(result)
}

fn wide_to_string(buf: &[u16]) -> String {
    let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
    String::from_utf16_lossy(&buf[..end])
}

/// 是否 64 位进程（64 位系统上 IsWow64Process=true 表示 32 位/WoW64）。
pub fn is_process_64bit(pid: u32) -> bool {
    unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if invalid_handle(handle) {
            return true;
        }
        let mut wow64: BOOL = 0;
        let ok = IsWow64Process(handle, &mut wow64) != 0;
        let _ = CloseHandle(handle);
        if !ok {
            return true;
        }
        wow64 == 0
    }
}

/// 已附加的进程句柄（可跨线程共享）。
pub struct ProcessHandle {
    handle: HANDLE,
    pid: u32,
}

unsafe impl Send for ProcessHandle {}
unsafe impl Sync for ProcessHandle {}

impl ProcessHandle {
    pub fn pid(&self) -> u32 {
        self.pid
    }

    /// 附加到进程。
    pub fn attach(pid: u32) -> MhResult<ProcessHandle> {
        unsafe {
            let handle = OpenProcess(
                PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION,
                0,
                pid,
            );
            if invalid_handle(handle) {
                return Err(MhError::Attach(format!(
                    "OpenProcess 失败 (pid={pid})，请以管理员身份运行"
                )));
            }
            Ok(ProcessHandle { handle, pid })
        }
    }

    /// 读取 count 个浮点数（小端），返回长度恒为 count。
    pub fn read_floats(&self, address: u64, count: usize, dt: DataType) -> MhResult<Vec<f64>> {
        if address == 0 {
            return Err(MhError::InvalidAddress(format!(
                "address is 0 or invalid: {address}"
            )));
        }
        if count == 0 {
            return Ok(Vec::new());
        }
        let elem = dt.elem_bytes();
        let size = count * elem;
        let mut buf = vec![0u8; size];
        let mut read: usize = 0;
        unsafe {
            let ok = ReadProcessMemory(
                self.handle,
                address as *const c_void,
                buf.as_mut_ptr() as *mut c_void,
                size,
                &mut read,
            );
            if ok == 0 || read != size {
                let code = std::io::Error::last_os_error().raw_os_error().unwrap_or(0);
                let msg = format!(
                    "ReadProcessMemory 失败 @ 0x{address:X} ({} x {})，win32err={code}",
                    count,
                    dt.as_str()
                );
                return Err(MhError::MemoryRead {
                    message: msg,
                    code: String::new(),
                });
            }
        }
        let mut out = Vec::with_capacity(count);
        if dt == DataType::Float {
            for i in 0..count {
                let b = &buf[i * 4..i * 4 + 4];
                out.push(f32::from_le_bytes([b[0], b[1], b[2], b[3]]) as f64);
            }
        } else {
            for i in 0..count {
                let mut arr = [0u8; 8];
                arr.copy_from_slice(&buf[i * 8..i * 8 + 8]);
                out.push(f64::from_le_bytes(arr));
            }
        }
        Ok(out)
    }
}

impl Drop for ProcessHandle {
    fn drop(&mut self) {
        unsafe {
            let _ = CloseHandle(self.handle);
        }
    }
}

// ----------------------------------------------------------------------
// 窗口
// ----------------------------------------------------------------------

struct WindowSearch {
    pid: u32,
    best_hwnd: HWND,
    best_area: i64,
}

unsafe extern "system" fn enum_windows_cb(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let search = &mut *(lparam as *mut WindowSearch);
    if IsWindowVisible(hwnd) == 0 {
        return 1;
    }
    if !GetParent(hwnd).is_null() {
        return 1;
    }
    let mut proc_id: u32 = 0;
    GetWindowThreadProcessId(hwnd, &mut proc_id);
    if proc_id != search.pid {
        return 1;
    }
    let mut rect = RECT {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
    };
    if GetClientRect(hwnd, &mut rect) != 0 {
        let area = (rect.right - rect.left) as i64 * (rect.bottom - rect.top) as i64;
        if area > search.best_area {
            search.best_area = area;
            search.best_hwnd = hwnd;
        }
    }
    1
}

/// 查找目标进程主窗口（可见、无父窗口、客户区最大）。
pub fn find_main_window(pid: u32) -> Option<HWND> {
    let mut search = WindowSearch {
        pid,
        best_hwnd: std::ptr::null_mut(),
        best_area: -1,
    };
    unsafe {
        EnumWindows(Some(enum_windows_cb), &mut search as *mut _ as LPARAM);
    }
    if search.best_hwnd.is_null() {
        None
    } else {
        Some(search.best_hwnd)
    }
}

/// 客户区在屏幕坐标系中的位置与大小（物理像素）。
pub fn get_client_rect_on_screen(hwnd: HWND) -> Option<(i32, i32, i32, i32)> {
    unsafe {
        if IsWindow(hwnd) == 0 {
            return None;
        }
        let mut rect = RECT {
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
        };
        if GetClientRect(hwnd, &mut rect) == 0 {
            return None;
        }
        let width = rect.right - rect.left;
        let height = rect.bottom - rect.top;
        let mut pt = POINT { x: 0, y: 0 };
        if ClientToScreen(hwnd, &mut pt) == 0 {
            return None;
        }
        Some((pt.x, pt.y, width, height))
    }
}

/// 窗口是否有效且可见（含最小化判定）。
pub fn is_window_visible(hwnd: HWND) -> bool {
    unsafe {
        if IsWindow(hwnd) == 0 {
            return false;
        }
        if IsWindowVisible(hwnd) == 0 {
            return false;
        }
        if IsIconic(hwnd) != 0 {
            return false;
        }
        true
    }
}

pub fn window_from_point(x: i32, y: i32) -> Option<HWND> {
    unsafe {
        let h = WindowFromPoint(POINT { x, y });
        if h.is_null() {
            None
        } else {
            Some(h)
        }
    }
}

pub fn get_cursor_pos() -> (i32, i32) {
    unsafe {
        let mut pt = POINT { x: 0, y: 0 };
        let _ = GetCursorPos(&mut pt);
        (pt.x, pt.y)
    }
}

pub fn window_pid(hwnd: HWND) -> u32 {
    unsafe {
        let mut pid: u32 = 0;
        GetWindowThreadProcessId(hwnd, &mut pid);
        pid
    }
}

pub fn window_title(hwnd: HWND) -> String {
    unsafe {
        let mut buf = [0u16; 512];
        let len = GetWindowTextW(hwnd, buf.as_mut_ptr(), buf.len() as i32);
        if len <= 0 {
            return String::new();
        }
        String::from_utf16_lossy(&buf[..len as usize])
    }
}

pub fn window_class(hwnd: HWND) -> String {
    unsafe {
        let mut buf = [0u16; 256];
        let len = GetClassNameW(hwnd, buf.as_mut_ptr(), buf.len() as i32);
        if len <= 0 {
            return String::new();
        }
        String::from_utf16_lossy(&buf[..len as usize])
    }
}

/// 设置鼠标穿透（WS_EX_TRANSPARENT | WS_EX_LAYERED）。
pub fn set_click_through(hwnd: HWND, enable: bool) {
    unsafe {
        let ex = GetWindowLongW(hwnd, GWL_EXSTYLE);
        let flags = (WS_EX_LAYERED | WS_EX_TRANSPARENT) as i32;
        let new_ex = if enable { ex | flags } else { ex & !flags };
        SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex);
    }
}

/// 置顶显示。
pub fn make_topmost(hwnd: HWND) {
    unsafe {
        SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        );
    }
}

/// 取顶层（根）窗口：WindowFromPoint 常返回子窗口，需要向上归到顶层。
pub fn root_window(hwnd: HWND) -> HWND {
    unsafe {
        let r = GetAncestor(hwnd, GA_ROOT);
        if r.is_null() {
            hwnd
        } else {
            r
        }
    }
}

/// 窗口完整边框矩形（屏幕坐标，物理像素），含标题栏与边框。
pub fn get_window_rect(hwnd: HWND) -> Option<(i32, i32, i32, i32)> {
    unsafe {
        if IsWindow(hwnd) == 0 {
            return None;
        }
        let mut rect = RECT {
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
        };
        if GetWindowRect(hwnd, &mut rect) == 0 {
            return None;
        }
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;
        if w <= 0 || h <= 0 {
            return None;
        }
        Some((rect.left, rect.top, w, h))
    }
}

/// 鼠标左键当前是否处于按下状态（全局，不受窗口焦点影响）。
pub fn is_lbutton_down() -> bool {
    unsafe { (GetAsyncKeyState(VK_LBUTTON as i32) as u16) & 0x8000 != 0 }
}

/// 主显示器尺寸（物理像素）。
pub fn primary_screen_size() -> (i32, i32) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetSystemMetrics, SM_CXSCREEN, SM_CYSCREEN};
    unsafe { (GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN)) }
}

/// 进程可执行文件名（不含路径）。
pub fn process_name(pid: u32) -> String {
    use windows_sys::Win32::System::Threading::QueryFullProcessImageNameW;
    unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if invalid_handle(handle) {
            return String::new();
        }
        let mut buf = [0u16; 512];
        let mut size = buf.len() as u32;
        let ok = QueryFullProcessImageNameW(handle, 0, buf.as_mut_ptr(), &mut size);
        let _ = CloseHandle(handle);
        if ok == 0 || size == 0 {
            return String::new();
        }
        let full = String::from_utf16_lossy(&buf[..size as usize]);
        full.rsplit('\\').next().unwrap_or(&full).to_string()
    }
}

/// 模块名匹配：忽略大小写与扩展名（`game.exe` 也能匹配 `game`）。
fn module_name_matches(found: &str, want: &str) -> bool {
    let f = found.trim().to_ascii_lowercase();
    let w = want.trim().to_ascii_lowercase();
    if f.is_empty() || w.is_empty() {
        return false;
    }
    if f == w {
        return true;
    }
    f.split('.').next() == w.split('.').next()
}

/// 目标进程中指定模块的基址（大小写不敏感，可省略扩展名）。
/// 供「模块名+偏移」地址写法解析使用；模块不存在时返回 None。
pub fn module_base(pid: u32, module: &str) -> Option<u64> {
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Module32FirstW, Module32NextW, MODULEENTRY32W,
        TH32CS_SNAPMODULE, TH32CS_SNAPMODULE32,
    };

    if module.trim().is_empty() {
        return None;
    }

    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
        if invalid_handle(snapshot) {
            return None;
        }
        let mut entry: MODULEENTRY32W = std::mem::zeroed();
        entry.dwSize = std::mem::size_of::<MODULEENTRY32W>() as u32;
        let mut base: Option<u64> = None;
        if Module32FirstW(snapshot, &mut entry) != 0 {
            loop {
                if module_name_matches(&wide_to_string(&entry.szModule), module) {
                    base = Some(entry.modBaseAddr as usize as u64);
                    break;
                }
                if Module32NextW(snapshot, &mut entry) == 0 {
                    break;
                }
            }
        }
        let _ = CloseHandle(snapshot);
        base.filter(|b| *b != 0)
    }
}

/// 进程完整可执行文件路径（含盘符）。
pub fn process_path(pid: u32) -> String {
    use windows_sys::Win32::System::Threading::QueryFullProcessImageNameW;
    unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if invalid_handle(handle) {
            return String::new();
        }
        let mut buf = [0u16; 1024];
        let mut size = buf.len() as u32;
        let ok = QueryFullProcessImageNameW(handle, 0, buf.as_mut_ptr(), &mut size);
        let _ = CloseHandle(handle);
        if ok == 0 || size == 0 {
            return String::new();
        }
        String::from_utf16_lossy(&buf[..size as usize])
    }
}

/// 窗口样式：返回 (style, ex_style)。
pub fn window_style(hwnd: HWND) -> (u32, u32) {
    unsafe {
        let style = GetWindowLongW(hwnd, GWL_STYLE) as u32;
        let ex = GetWindowLongW(hwnd, GWL_EXSTYLE) as u32;
        (style, ex)
    }
}

/// 某个窗口的完整信息（供「窗口信息」面板展示）。
#[derive(Debug, Clone, Serialize)]
pub struct WindowDetailInfo {
    pub hwnd: String,
    pub pid: u32,
    pub name: String,
    pub path: String,
    pub title: String,
    pub class_name: String,
    pub is_64bit: bool,
    pub win_x: i32,
    pub win_y: i32,
    pub win_w: i32,
    pub win_h: i32,
    pub client_x: i32,
    pub client_y: i32,
    pub client_w: i32,
    pub client_h: i32,
    pub style: String,
    pub ex_style: String,
}

/// 上一次本进程 CPU 时间与采样时刻，用于计算本程序 CPU 占用增量。
static PERF_LAST: std::sync::Mutex<Option<(u64, std::time::Instant)>> =
    std::sync::Mutex::new(None);

/// 本程序性能快照（只统计自身对整个硬件的占用）。
#[derive(Debug, Clone, Serialize)]
pub struct PerfSnapshot {
    /// 本程序 CPU 占用（占整机 CPU 的百分比）
    pub cpu_percent: f64,
    /// 本程序内存工作集（MB）
    pub mem_mb: u64,
    /// 本程序内存占系统物理内存的百分比
    pub mem_percent: f64,
}

/// 采集一次本程序性能数据。CPU 为两次采样之间的平均占用（首次调用返回 0）。
pub fn perf_snapshot() -> PerfSnapshot {
    use windows_sys::Win32::System::ProcessStatus::{
        GetProcessMemoryInfo, PROCESS_MEMORY_COUNTERS,
    };
    use windows_sys::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, GetProcessTimes};

    let to_u64 = |f: FILETIME| ((f.dwHighDateTime as u64) << 32) | f.dwLowDateTime as u64;
    let handle = unsafe { GetCurrentProcess() };

    // 本进程累计 CPU 时间（kernel + user，单位 100ns）
    let mut proc_time = 0u64;
    unsafe {
        let mut creation: FILETIME = std::mem::zeroed();
        let mut exit: FILETIME = std::mem::zeroed();
        let mut kernel: FILETIME = std::mem::zeroed();
        let mut user: FILETIME = std::mem::zeroed();
        if GetProcessTimes(handle, &mut creation, &mut exit, &mut kernel, &mut user) != 0 {
            proc_time = to_u64(kernel) + to_u64(user);
        }
    }

    let cores = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1) as f64;
    let now = std::time::Instant::now();
    let mut cpu_percent = 0.0f64;
    {
        let mut guard = PERF_LAST.lock().unwrap();
        if let Some((prev_time, prev_instant)) = *guard {
            let dt = now.duration_since(prev_instant).as_secs_f64();
            let cpu_secs = proc_time.saturating_sub(prev_time) as f64 / 1e7;
            if dt > 0.0 {
                // 除以核心数 => 占整机 CPU 的百分比
                cpu_percent = cpu_secs / dt / cores * 100.0;
            }
        }
        *guard = Some((proc_time, now));
    }

    // 本进程内存工作集
    let mut mem_mb = 0u64;
    unsafe {
        let mut pmc: PROCESS_MEMORY_COUNTERS = std::mem::zeroed();
        pmc.cb = std::mem::size_of::<PROCESS_MEMORY_COUNTERS>() as u32;
        if GetProcessMemoryInfo(handle, &mut pmc, pmc.cb) != 0 {
            mem_mb = pmc.WorkingSetSize as u64 / (1024 * 1024);
        }
    }

    // 系统物理内存总量（仅用于换算占用百分比）
    let mut total_mb = 0u64;
    unsafe {
        let mut ms: MEMORYSTATUSEX = std::mem::zeroed();
        ms.dwLength = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
        if GlobalMemoryStatusEx(&mut ms) != 0 {
            total_mb = ms.ullTotalPhys / (1024 * 1024);
        }
    }
    let mem_percent = if total_mb > 0 {
        mem_mb as f64 / total_mb as f64 * 100.0
    } else {
        0.0
    };

    PerfSnapshot {
        cpu_percent,
        mem_mb,
        mem_percent,
    }
}

pub fn window_detail_info(pid: u32, hwnd: HWND) -> WindowDetailInfo {
    let (win_x, win_y, win_w, win_h) = get_window_rect(hwnd).unwrap_or((0, 0, 0, 0));
    let (client_x, client_y, client_w, client_h) =
        get_client_rect_on_screen(hwnd).unwrap_or((0, 0, 0, 0));
    let (style, ex_style) = window_style(hwnd);
    WindowDetailInfo {
        hwnd: format!("0x{:X}", hwnd as usize),
        pid,
        name: process_name(pid),
        path: process_path(pid),
        title: window_title(hwnd),
        class_name: window_class(hwnd),
        is_64bit: is_process_64bit(pid),
        win_x,
        win_y,
        win_w,
        win_h,
        client_x,
        client_y,
        client_w,
        client_h,
        style: format!("0x{style:08X}"),
        ex_style: format!("0x{ex_style:08X}"),
    }
}
