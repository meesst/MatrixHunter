//! 核心数据结构（对应原 core/scheme.py）。

use serde::{Deserialize, Serialize};

/// 数据类型（§5.1）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DataType {
    Float,
    Double,
}

impl DataType {
    pub fn elem_bytes(self) -> usize {
        match self {
            DataType::Float => 4,
            DataType::Double => 8,
        }
    }
    pub fn as_str(self) -> &'static str {
        match self {
            DataType::Float => "float",
            DataType::Double => "double",
        }
    }
}

/// 矩阵形状。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MatrixShape {
    #[serde(rename = "4x4")]
    Full4x4,
    #[serde(rename = "3x4")]
    Row3x4,
}

impl MatrixShape {
    pub fn as_str(self) -> &'static str {
        match self {
            MatrixShape::Full4x4 => "4x4",
            MatrixShape::Row3x4 => "3x4",
        }
    }
}

/// 内存布局。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MemoryLayout {
    RowMajor,
    ColMajor,
}

impl MemoryLayout {
    pub fn as_str(self) -> &'static str {
        match self {
            MemoryLayout::RowMajor => "row_major",
            MemoryLayout::ColMajor => "col_major",
        }
    }
}

/// 乘法方向。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MulDirection {
    #[serde(rename = "v*M")]
    VecMulM,
    #[serde(rename = "M*v")]
    MMulVec,
}

impl MulDirection {
    pub fn as_str(self) -> &'static str {
        match self {
            MulDirection::VecMulM => "v*M",
            MulDirection::MMulVec => "M*v",
        }
    }
}

/// clip-w 符号。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ClipWSign {
    #[serde(rename = "+w")]
    Positive,
    #[serde(rename = "-w")]
    Negative,
}

impl ClipWSign {
    pub fn as_str(self) -> &'static str {
        match self {
            ClipWSign::Positive => "+w",
            ClipWSign::Negative => "-w",
        }
    }
}

/// 屏幕象限。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Quadrant {
    TL,
    TR,
    BL,
    BR,
}

impl Quadrant {
    pub fn as_str(self) -> &'static str {
        match self {
            Quadrant::TL => "TL",
            Quadrant::TR => "TR",
            Quadrant::BL => "BL",
            Quadrant::BR => "BR",
        }
    }
}

/// 方案状态。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SchemeStatus {
    Active,
    Eliminated,
}

/// 一个地址的一种完整矩阵解释方案（不可变）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MatrixScheme {
    pub scheme_id: String,
    pub address: u64,
    pub data_type: DataType,
    pub shape: MatrixShape,
    pub layout: MemoryLayout,
    pub mul_direction: MulDirection,
    pub clip_w_sign: ClipWSign,
}

impl MatrixScheme {
    /// 需读取的浮点数个数。
    pub fn element_count(&self) -> usize {
        match self.shape {
            MatrixShape::Full4x4 => 16,
            MatrixShape::Row3x4 => 12,
        }
    }

    /// 需读取的字节数。
    pub fn byte_size(&self) -> usize {
        self.element_count() * self.data_type.elem_bytes()
    }

    /// 人类可读描述（结果表展示）。
    pub fn description(&self) -> String {
        let layout_str = match self.layout {
            MemoryLayout::RowMajor => "行主序",
            MemoryLayout::ColMajor => "列主序",
        };
        let mul_str = match self.mul_direction {
            MulDirection::VecMulM => "向量×矩阵",
            MulDirection::MMulVec => "矩阵×向量",
        };
        format!(
            "{} {} {} {} {}",
            self.shape.as_str(),
            layout_str,
            mul_str,
            self.clip_w_sign.as_str(),
            self.data_type.as_str()
        )
    }

    /// 将原始浮点数构建为 4x4 矩阵（§7.1）。
    /// raw.len() 必须 >= element_count。
    pub fn build_matrix(&self, raw: &[f64]) -> Option<[[f64; 4]; 4]> {
        if raw.len() < self.element_count() {
            return None;
        }
        let mut m = [[0.0f64; 4]; 4];
        match self.shape {
            MatrixShape::Full4x4 => match self.layout {
                MemoryLayout::RowMajor => {
                    for i in 0..4 {
                        for j in 0..4 {
                            m[i][j] = raw[i * 4 + j];
                        }
                    }
                }
                MemoryLayout::ColMajor => {
                    for i in 0..4 {
                        for j in 0..4 {
                            m[i][j] = raw[j * 4 + i];
                        }
                    }
                }
            },
            MatrixShape::Row3x4 => {
                for i in 0..3 {
                    for j in 0..4 {
                        m[i][j] = raw[i * 4 + j];
                    }
                }
                m[3] = [0.0, 0.0, 0.0, 1.0];
            }
        }
        Some(m)
    }
}

/// 世界坐标 W。
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct WorldCoord {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

/// 投影结果（§5.4）。
#[derive(Debug, Clone, Serialize)]
pub struct ProjectionResult {
    pub visible: bool,
    pub screen_x: f64,
    pub screen_y: f64,
    pub quadrant: Option<Quadrant>,
    pub clip_w: f64,
    pub reason: String,
    pub borderline: bool,
}

/// 过滤结果（§5.5）。
#[derive(Debug, Clone, Serialize)]
pub struct FilterOutcome {
    pub before_count: usize,
    pub after_count: usize,
    pub eliminated_ids: Vec<String>,
    pub skipped_ids: Vec<String>,
    pub auto_rolled_back: bool,
}

/// 每个地址统一读取的元素数（覆盖 4x4=16 与 3x4=12）。
pub const READ_ELEMENT_COUNT: usize = 16;
