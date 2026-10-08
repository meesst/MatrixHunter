//! 矩阵枚举 / 投影 / 过滤引擎（对应 core/matrix_enumerator.py + core/projector.py + core/filter_engine.py）。

use crate::errors::{MhError, MhResult};
use crate::model::*;

/// 近边界阈值。
pub const BORDERLINE_W: f64 = 6.0;
/// clip-w 最小有效值。
pub const CLIP_W_EPSILON: f64 = 1e-6;
/// clip-w 最大可接受值。
pub const CLIP_W_MAX: f64 = 1e7;

// ----------------------------------------------------------------------
// 矩阵枚举
// ----------------------------------------------------------------------

pub struct MatrixGenerator;

impl MatrixGenerator {
    /// 为单个地址生成全部方案。
    ///
    /// 布局与方向两维的 4 种组合里存在冗余：
    ///   - 列主序读出的矩阵 = 行主序读出的矩阵的转置；
    ///   - 「向量×矩阵」与「矩阵×向量」的结果也互为转置。
    /// 两者同时翻转时转置相互抵消，得到逐元素完全相同的结果：
    ///   (行主序, v*M) ≡ (列主序, M*v)
    ///   (行主序, M*v) ≡ (列主序, v*M)
    /// 因此布局这一维固定为行主序、只保留 2 个方向即可：
    ///   形状(2) × 方向(2) × 符号(2) = 8 种。
    pub fn generate(address: u64, dt: DataType) -> Vec<MatrixScheme> {
        let shapes = [MatrixShape::Full4x4, MatrixShape::Row3x4];
        let layouts = [MemoryLayout::RowMajor];
        let muls = [MulDirection::VecMulM, MulDirection::MMulVec];
        let signs = [ClipWSign::Positive, ClipWSign::Negative];
        let mut out = Vec::with_capacity(8);
        for shape in shapes {
            for layout in layouts {
                for mul in muls {
                    for sign in signs {
                        let scheme_id = format!(
                            "0x{:X}:{}:{}:{}:{}:{}",
                            address,
                            shape.as_str(),
                            layout.as_str(),
                            mul.as_str(),
                            sign.as_str(),
                            dt.as_str()
                        );
                        out.push(MatrixScheme {
                            scheme_id,
                            address,
                            data_type: dt,
                            shape,
                            layout,
                            mul_direction: mul,
                            clip_w_sign: sign,
                        });
                    }
                }
            }
        }
        out
    }
}

// ----------------------------------------------------------------------
// 投影
// ----------------------------------------------------------------------

fn all_finite(v: &[f64]) -> bool {
    v.iter().all(|x| x.is_finite())
}

fn invisible(reason: String) -> ProjectionResult {
    ProjectionResult {
        visible: false,
        screen_x: 0.0,
        screen_y: 0.0,
        quadrant: None,
        clip_w: 0.0,
        reason,
        borderline: false,
    }
}

/// 用已构建的 4x4 矩阵投影世界坐标（§5.4 完整算法，必须逐条复刻）。
pub fn project_with_matrix(
    m: &[[f64; 4]; 4],
    dir: MulDirection,
    sign: ClipWSign,
    w: WorldCoord,
    screen_w: i32,
    screen_h: i32,
) -> ProjectionResult {
    if !all_finite(&[w.x, w.y, w.z]) {
        return invisible("WorldCoord 含非有限值".to_string());
    }
    let v = [w.x, w.y, w.z, 1.0];
    let mut t = [0.0f64; 4];
    match dir {
        MulDirection::VecMulM => {
            for j in 0..4 {
                let mut s = 0.0;
                for i in 0..4 {
                    s += v[i] * m[i][j];
                }
                t[j] = s;
            }
        }
        MulDirection::MMulVec => {
            for i in 0..4 {
                let mut s = 0.0;
                for j in 0..4 {
                    s += m[i][j] * v[j];
                }
                t[i] = s;
            }
        }
    }

    if !all_finite(&t) {
        return invisible("变换结果含非有限值".to_string());
    }

    let clip_w = match sign {
        ClipWSign::Positive => t[3],
        ClipWSign::Negative => -t[3],
    };

    if clip_w - CLIP_W_EPSILON <= 0.0 {
        return invisible(format!(
            "clip-w = {:.6e} ≤ 0（位于相机后方）",
            clip_w
        ));
    }
    if clip_w > CLIP_W_MAX {
        return invisible(format!("clip-w 过大 ({:.3e})", clip_w));
    }

    let borderline = clip_w.abs() > BORDERLINE_W;

    let nd_x = t[0] / clip_w;
    let nd_y = t[1] / clip_w;
    let nd_z = t[2] / clip_w;

    let clip_x = nd_x * 0.5 + 0.5;
    let clip_y = 1.0 - (nd_y * 0.5 + 0.5);

    if !(0.0..=1.0).contains(&clip_x) || !(0.0..=1.0).contains(&clip_y) {
        return invisible(format!(
            "屏幕坐标越界 (cx={clip_x:.3}, cy={clip_y:.3})"
        ));
    }

    let quadrant = match (clip_x >= 0.5, clip_y >= 0.5) {
        (false, false) => Quadrant::TL,
        (true, false) => Quadrant::TR,
        (false, true) => Quadrant::BL,
        (true, true) => Quadrant::BR,
    };

    let _ = nd_z;
    ProjectionResult {
        visible: true,
        screen_x: clip_x * screen_w as f64,
        screen_y: clip_y * screen_h as f64,
        quadrant: Some(quadrant),
        clip_w,
        reason: "ok".to_string(),
        borderline,
    }
}

/// 便捷：从原始浮点数构建矩阵后投影。
pub fn project_from_raw(
    scheme: &MatrixScheme,
    raw: &[f64],
    w: WorldCoord,
    screen_w: i32,
    screen_h: i32,
) -> MhResult<ProjectionResult> {
    let m = scheme
        .build_matrix(raw)
        .ok_or_else(|| MhError::Enumeration("原始数据长度不足，无法构建矩阵".to_string()))?;
    Ok(project_with_matrix(
        &m,
        scheme.mul_direction,
        scheme.clip_w_sign,
        w,
        screen_w,
        screen_h,
    ))
}

// ----------------------------------------------------------------------
// 过滤引擎
// ----------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SchemeState {
    Active,
    Eliminated,
}

#[derive(Debug, Clone)]
pub struct PoolEntry {
    pub scheme: MatrixScheme,
    pub state: SchemeState,
    /// 连续读取失败的轮数：地址当前不可读（如 win32err=299）时累加，读取成功清零。
    /// 达到 `READ_FAIL_ELIMINATE_ROUNDS` 即淘汰，避免不可读地址永远卡在池里。
    pub read_fail_streak: u32,
}

/// 连续多少轮读取失败后淘汰该地址。
/// 取 2 是留一次容错：偶发失败先保留，再点一次过滤仍失败才剔除。
pub const READ_FAIL_ELIMINATE_ROUNDS: u32 = 2;

#[derive(Debug, Default)]
pub struct FilterState {
    pub pool: Vec<PoolEntry>,
    pub undo_stack: Vec<Vec<PoolEntry>>,
    pub selected_id: Option<String>,
}

impl FilterState {
    pub fn clear(&mut self) {
        self.pool.clear();
        self.undo_stack.clear();
        self.selected_id = None;
    }

    /// 装入新的一批方案（新的枚举结果）。
    pub fn load(&mut self, schemes: Vec<MatrixScheme>) {
        self.pool = schemes
            .into_iter()
            .map(|s| PoolEntry {
                scheme: s,
                state: SchemeState::Active,
                read_fail_streak: 0,
            })
            .collect();
        self.undo_stack.clear();
        self.selected_id = None;
    }

    pub fn active_if_present(&self, id: &str) -> bool {
        self.pool
            .iter()
            .any(|e| e.scheme.scheme_id == id && e.state == SchemeState::Active)
    }

    pub fn select(&mut self, id: &str) -> bool {
        if self.active_if_present(id) {
            self.selected_id = Some(id.to_string());
            true
        } else {
            false
        }
    }

    pub fn remove(&mut self, id: &str) -> bool {
        let before = self.pool.len();
        self.pool.retain(|e| e.scheme.scheme_id != id);
        if self.selected_id.as_deref() == Some(id) {
            self.selected_id = None;
        }
        self.undo_stack.clear();
        self.pool.len() != before
    }

    /// 应用一轮过滤（§5.5）。
    pub fn apply<F>(&mut self, quadrant: Quadrant, world: WorldCoord, screen_w: i32, screen_h: i32, mut reader: F) -> FilterOutcome
    where
        F: FnMut(u64, DataType) -> MhResult<Vec<f64>>,
    {
        let snapshot = self.pool.clone();
        let before_count = self.pool.len();
        let mut eliminated_ids: Vec<String> = Vec::new();
        let mut skipped_ids: Vec<String> = Vec::new();

        // 读取缓存：同一地址只读一次
        let mut cache: std::collections::HashMap<u64, Option<Vec<f64>>> =
            std::collections::HashMap::new();

        for entry in self.pool.iter_mut() {
            if entry.state == SchemeState::Eliminated {
                continue;
            }
            let addr = entry.scheme.address;
            if !cache.contains_key(&addr) {
                let res = reader(addr, entry.scheme.data_type)
                    .ok()
                    .filter(|r| r.len() >= entry.scheme.element_count());
                cache.insert(addr, res);
            }
            let raw = match cache.get(&addr).and_then(|o| o.clone()) {
                Some(r) => r,
                None => {
                    // 地址当前不可读（如 win32err=299）：只跳过会导致它永远留在池里，
                    // 因此连续失败到阈值就淘汰，让过滤能收敛。
                    entry.read_fail_streak += 1;
                    if entry.read_fail_streak >= READ_FAIL_ELIMINATE_ROUNDS {
                        entry.state = SchemeState::Eliminated;
                        eliminated_ids.push(entry.scheme.scheme_id.clone());
                    } else {
                        skipped_ids.push(entry.scheme.scheme_id.clone());
                    }
                    continue;
                }
            };
            entry.read_fail_streak = 0;
            match project_from_raw(&entry.scheme, &raw, world, screen_w, screen_h) {
                Ok(p) => {
                    let keep = p.visible && p.quadrant == Some(quadrant);
                    if !keep {
                        entry.state = SchemeState::Eliminated;
                        eliminated_ids.push(entry.scheme.scheme_id.clone());
                    }
                }
                Err(_) => {
                    skipped_ids.push(entry.scheme.scheme_id.clone());
                }
            }
        }

        let after_count = self
            .pool
            .iter()
            .filter(|e| e.state == SchemeState::Active)
            .count();

        let mut auto_rolled_back = false;
        if after_count == 0 {
            self.pool = snapshot;
            eliminated_ids.clear();
            auto_rolled_back = true;
            if let Some(sel) = &self.selected_id {
                if !self.active_if_present(sel) {
                    self.selected_id = None;
                }
            }
        } else {
            self.undo_stack.push(snapshot);
        }

        FilterOutcome {
            before_count,
            after_count,
            eliminated_ids,
            skipped_ids,
            auto_rolled_back,
        }
    }

    /// 撤销上一轮过滤。
    pub fn undo(&mut self) -> Option<usize> {
        if self.undo_stack.is_empty() {
            return None;
        }
        let snapshot = self.undo_stack.pop().unwrap();
        let count = snapshot.len();
        self.pool = snapshot;
        if let Some(sel) = &self.selected_id {
            if !self.active_if_present(sel) {
                self.selected_id = None;
            }
        }
        Some(count)
    }

    pub fn active_count(&self) -> usize {
        self.pool
            .iter()
            .filter(|e| e.state == SchemeState::Active)
            .count()
    }

    pub fn active_schemes(&self) -> Vec<MatrixScheme> {
        self.pool
            .iter()
            .filter(|e| e.state == SchemeState::Active)
            .map(|e| e.scheme.clone())
            .collect()
    }

    pub fn selected_scheme(&self) -> Option<MatrixScheme> {
        let id = self.selected_id.as_ref()?;
        self.pool
            .iter()
            .find(|e| e.scheme.scheme_id == *id && e.state == SchemeState::Active)
            .map(|e| e.scheme.clone())
    }
}
