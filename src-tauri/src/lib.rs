//! MatrixHunter 主入口：注册状态、创建叠加层窗口、启动后台线程、注册命令。

pub mod commands;
pub mod config;
pub mod engine;
pub mod errors;
pub mod model;
pub mod runtime;
pub mod state;
pub mod win32;

use std::sync::Arc;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();
            let state = Arc::new(AppState::new());
            app.manage(state.clone());

            // 叠加层窗口：透明、无边框、置顶、默认鼠标穿透、不可见。
            let overlay = WebviewWindowBuilder::new(
                app,
                "overlay",
                WebviewUrl::App("index.html".into()),
            )
            .title("MatrixHunter Overlay")
            .transparent(true)
            .decorations(false)
            .always_on_top(true)
            .skip_taskbar(true)
            .shadow(false)
            .resizable(false)
            .focused(false)
            .visible(false)
            .build();

            if let Ok(win) = overlay {
                let _ = win.set_ignore_cursor_events(true);
                if let Ok(h) = win.hwnd() {
                    win32::set_click_through(h.0 as _, true);
                    win32::make_topmost(h.0 as _);
                }
            }

            // 拖拽选取层：全屏透明、点击穿透、置顶、默认不可见。
            let picker = WebviewWindowBuilder::new(
                app,
                "picker",
                WebviewUrl::App("index.html".into()),
            )
            .title("MatrixHunter Picker")
            .transparent(true)
            .decorations(false)
            .always_on_top(true)
            .skip_taskbar(true)
            .shadow(false)
            .resizable(false)
            .focused(false)
            .visible(false)
            .build();

            if let Ok(win) = picker {
                let _ = win.set_ignore_cursor_events(true);
                if let Ok(h) = win.hwnd() {
                    win32::set_click_through(h.0 as _, true);
                    win32::make_topmost(h.0 as _);
                }
            }

            // 后台线程
            runtime::start_monitor(handle.clone(), state.clone());
            runtime::start_realtime(handle.clone(), state.clone());
            runtime::start_bone(handle.clone(), state.clone());

            Ok(())
        })
        // 关闭主窗口 = 退出整个进程。
        // 否则 overlay / picker 两个常驻隐藏窗口（skip_taskbar）会继续存活，
        // Tauri 事件循环不结束，进程就驻留后台且任务栏无图标。
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let tauri::WindowEvent::CloseRequested { .. } = event {
                    window.app_handle().exit(0);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::list_processes,
            commands::attach_process,
            commands::detach_process,
            commands::window_under_cursor,
            commands::start_pick,
            commands::refresh_target_window,
            commands::window_detail,
            commands::set_size_override,
            commands::enumerate,
            commands::filter,
            commands::bone_apply_filter,
            commands::undo_filter,
            commands::reset_pool,
            commands::remove_scheme,
            commands::select_scheme,
            commands::get_pool_summary,
            commands::get_active_schemes,
            commands::get_all_schemes,
            commands::preview_scheme,
            commands::stop_preview,
            commands::start_realtime,
            commands::stop_realtime,
            commands::set_world,
            commands::set_bone_config,
            commands::set_frame_config,
            commands::app_info,
            commands::perf_snapshot,
            commands::read_address,
            commands::save_settings,
            commands::load_settings,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
