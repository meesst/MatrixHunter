//! 设置持久化（对应原 infra/config.py，存到用户配置目录 JSON）。

use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

use crate::errors::{MhError, MhResult};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub addresses: String,
    pub data_type: String,
    pub quadrant: String,
    pub world_x: f64,
    pub world_y: f64,
    pub world_z: f64,
    pub size_w: i32,
    pub size_h: i32,
    /// 窗口跟随 / 实时点 / 骨骼帧的刷新间隔（毫秒）
    pub frame_follow_ms: u64,
    pub frame_realtime_ms: u64,
    pub frame_bone_ms: u64,
    pub bone_base: String,
    pub bone_count: usize,
    pub bone_stride: usize,
    pub bone_addr: String,
    pub bone_hidden: String,
    pub bone_conn: String,
    pub bone_show_labels: bool,
    pub bone_show_lines: bool,
    pub bone_show_joints: bool,
    pub bone_point_mode: String,
    pub bone_font_size: f64,
    pub bone_font_color: String,
    pub bone_line_color: String,
    pub bone_line_width: f64,
    pub bone_point_radius: f64,
    pub bone_point_outline_width: f64,
    pub bone_point_color: String,
    pub bone_enabled: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            addresses: String::new(),
            data_type: "float".to_string(),
            quadrant: "TL".to_string(),
            world_x: 0.0,
            world_y: 0.0,
            world_z: 0.0,
            size_w: 0,
            size_h: 0,
            frame_follow_ms: 16,
            frame_realtime_ms: 25,
            frame_bone_ms: 70,
            bone_base: String::new(),
            bone_count: 0,
            bone_stride: 16,
            bone_addr: String::new(),
            bone_hidden: String::new(),
            bone_conn: String::new(),
            bone_show_labels: true,
            bone_show_lines: true,
            bone_show_joints: true,
            bone_point_mode: "label".to_string(),
            bone_font_size: 13.0,
            bone_font_color: "#FFD54A".to_string(),
            bone_line_color: "#35E0FF".to_string(),
            bone_line_width: 1.6,
            bone_point_radius: 3.2,
            bone_point_outline_width: 1.6,
            bone_point_color: "#35E0FF".to_string(),
            bone_enabled: false,
        }
    }
}

fn settings_path(app: &AppHandle) -> MhResult<PathBuf> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| MhError::Other(format!("无法获取配置目录: {e}")))?;
    Ok(dir.join("settings.json"))
}

pub fn load(app: &AppHandle) -> Settings {
    match settings_path(app) {
        Ok(p) => match fs::read_to_string(&p) {
            Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
            Err(_) => Settings::default(),
        },
        Err(_) => Settings::default(),
    }
}

pub fn save(app: &AppHandle, s: &Settings) -> MhResult<()> {
    let p = settings_path(app)?;
    if let Some(parent) = p.parent() {
        fs::create_dir_all(parent).map_err(|e| MhError::Other(format!("创建配置目录失败: {e}")))?;
    }
    let text =
        serde_json::to_string_pretty(s).map_err(|e| MhError::Other(format!("序列化失败: {e}")))?;
    fs::write(&p, text).map_err(|e| MhError::Other(format!("写入配置失败: {e}")))?;
    Ok(())
}
