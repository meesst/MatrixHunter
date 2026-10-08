//! 全局应用状态（对应原 ui/main_window.py 维护的运行时字段）。

use std::sync::{Arc, Mutex};

use crate::engine::FilterState;
use crate::model::{DataType, WorldCoord};
use crate::win32::ProcessHandle;

#[derive(Debug, Clone)]
pub struct RealtimeState {
    pub running: bool,
    pub failure: Option<String>,
}

impl Default for RealtimeState {
    fn default() -> Self {
        RealtimeState {
            running: false,
            failure: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct BoneState {
    pub enabled: bool,
    pub base_address: u64,
    pub count: usize,
    pub stride: usize,
    pub address: u64,
    /// 只绘制这些序号的文本；为空表示全部。仅影响序号文字，不影响连线与关节。
    pub hidden: Vec<usize>,
    pub connections: Vec<(usize, usize)>,
    /// 各绘制要素的开关（替代「数值 0 即不绘制」）。
    pub show_labels: bool,
    pub show_lines: bool,
    pub show_joints: bool,
    /// 点位筛选模式：`label` = 以「显示序号」白名单为准；`links` = 以「连接关系」为准。
    pub point_mode: String,
    pub font_size: f64,
    pub font_color: String,
    pub line_color: String,
    pub line_width: f64,
    pub point_radius: f64,
    /// 关节轮廓粗细（与连线粗细独立）。
    pub point_outline_width: f64,
    pub point_color: String,
    pub data_type: DataType,
}

impl Default for BoneState {
    fn default() -> Self {
        BoneState {
            enabled: false,
            base_address: 0,
            count: 0,
            stride: 16,
            address: 0,
            hidden: Vec::new(),
            connections: Vec::new(),
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
            data_type: DataType::Float,
        }
    }
}

/// 绘制 / 跟随频率（毫秒）。数值越小越跟手，代价是 CPU 占用略高。
#[derive(Debug, Clone)]
pub struct FrameConfig {
    /// 窗口跟随（叠加层对齐目标客户区）的轮询间隔
    pub follow_ms: u64,
    /// 实时点刷新间隔
    pub realtime_ms: u64,
    /// 骨骼帧刷新间隔
    pub bone_ms: u64,
}

impl Default for FrameConfig {
    fn default() -> Self {
        FrameConfig {
            follow_ms: 16,
            realtime_ms: 25,
            bone_ms: 70,
        }
    }
}

pub struct AppState {
    pub process: Mutex<Option<Arc<ProcessHandle>>>,
    pub pid: Mutex<Option<u32>>,
    pub hwnd: Mutex<Option<isize>>,
    pub client_offset: Mutex<(i32, i32)>,
    pub client_size: Mutex<(i32, i32)>,
    /// 手动覆盖的客户区尺寸；None 表示跟随真实窗口。
    pub size_override: Mutex<Option<(i32, i32)>>,
    pub filter: Mutex<FilterState>,
    pub realtime: Mutex<RealtimeState>,
    /// 界面填写的目标世界坐标（投影输入）。
    /// 实时点与预览都用它，而不是鼠标位置。
    pub world: Mutex<WorldCoord>,
    pub bone: Mutex<BoneState>,
    pub frame: Mutex<FrameConfig>,
    /// 单步读取失败提示（非致命）。
    pub last_failure: Mutex<Option<String>>,
}

impl AppState {
    pub fn new() -> Self {
        AppState {
            process: Mutex::new(None),
            pid: Mutex::new(None),
            hwnd: Mutex::new(None),
            client_offset: Mutex::new((0, 0)),
            client_size: Mutex::new((0, 0)),
            size_override: Mutex::new(None),
            filter: Mutex::new(FilterState::default()),
            realtime: Mutex::new(RealtimeState::default()),
            world: Mutex::new(WorldCoord {
                x: 0.0,
                y: 0.0,
                z: 0.0,
            }),
            bone: Mutex::new(BoneState::default()),
            frame: Mutex::new(FrameConfig::default()),
            last_failure: Mutex::new(None),
        }
    }

    /// 当前生效的客户区尺寸（优先手动覆盖）。
    pub fn effective_size(&self) -> (i32, i32) {
        if let Some(ov) = *self.size_override.lock().unwrap() {
            return ov;
        }
        *self.client_size.lock().unwrap()
    }

    pub fn process_arc(&self) -> Option<Arc<ProcessHandle>> {
        self.process.lock().unwrap().clone()
    }

    pub fn is_attached(&self) -> bool {
        self.process.lock().unwrap().is_some()
    }

    /// 读取指定地址的 16 个浮点数（统一读取量）。
    pub fn read_elements(&self, address: u64, dt: DataType) -> crate::errors::MhResult<Vec<f64>> {
        let p = self
            .process_arc()
            .ok_or_else(|| crate::errors::MhError::Attach("尚未附加进程".to_string()))?;
        p.read_floats(address, crate::model::READ_ELEMENT_COUNT, dt)
    }
}
