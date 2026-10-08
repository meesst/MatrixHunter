export type DataType = "float" | "double";
export type Quadrant = "TL" | "TR" | "BL" | "BR";

/* ---------------- 界面外观 ---------------- */
export type ThemeMode = "dark" | "light" | "system";
export type AccentId = "blue" | "cyan" | "violet" | "green" | "amber";

/** 象限参照十字线的可选颜色 */
export const LINE_COLORS: { id: string; label: string; c: string }[] = [
  { id: "cyan", label: "青", c: "#35E0FF" },
  { id: "blue", label: "蓝", c: "#4C8DFF" },
  { id: "green", label: "绿", c: "#3DDC84" },
  { id: "amber", label: "橙", c: "#FFB545" },
  { id: "pink", label: "粉", c: "#FF5C8A" },
  { id: "violet", label: "紫", c: "#C77DFF" },
  { id: "white", label: "白", c: "#FFFFFF" },
];

export const ACCENTS: { id: AccentId; label: string; c1: string; c2: string }[] = [
  { id: "blue", label: "苍穹蓝", c1: "#5b8cff", c2: "#3fe3ff" },
  { id: "cyan", label: "青碧", c1: "#14b8d4", c2: "#6fe9ff" },
  { id: "violet", label: "紫罗兰", c1: "#8b6cff", c2: "#c39bff" },
  { id: "green", label: "松绿", c1: "#1fae63", c2: "#6ce6a2" },
  { id: "amber", label: "琥珀", c1: "#e0902a", c2: "#ffc85c" },
];

export interface WorldCoord {
  x: number;
  y: number;
  z: number;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  is_64bit: boolean;
}

export interface AttachInfo {
  pid: number;
  name: string;
  hwnd_found: boolean;
  client_x: number;
  client_y: number;
  client_w: number;
  client_h: number;
}

/** 硬件 / 本进程性能快照。 */
export interface PerfSnapshot {
  cpu_percent: number;
  mem_mb: number;
  mem_percent: number;
}

/** 窗口 / 进程详情（「窗口信息」面板）。 */
export interface WindowDetail {
  hwnd: string;
  pid: number;
  name: string;
  path: string;
  title: string;
  class_name: string;
  is_64bit: boolean;
  win_x: number;
  win_y: number;
  win_w: number;
  win_h: number;
  client_x: number;
  client_y: number;
  client_w: number;
  client_h: number;
  style: string;
  ex_style: string;
}

export interface PickHover {
  x: number;
  y: number;
  w: number;
  h: number;
  pid: number;
  name: string;
  title: string;
}

export interface PickDone {
  ok: boolean;
  pid: number;
  name: string;
  title: string;
  reason: string;
}

export interface WindowUnderCursor {
  pid: number;
  name: string;
  title: string;
  class_name: string;
  hwnd_found: boolean;
}

export type SchemeStatus = "active" | "eliminated";

export interface SchemeView {
  scheme_id: string;
  address: number;
  address_hex: string;
  description: string;
  data_type: string;
  shape: string;
  layout: string;
  mul_direction: string;
  clip_w_sign: string;
  status: SchemeStatus;
}

export interface EnumerateResult {
  schemes: SchemeView[];
  invalid: string[];
  total: number;
}

export interface FilterOutcome {
  before_count: number;
  after_count: number;
  eliminated_ids: string[];
  skipped_ids: string[];
  auto_rolled_back: boolean;
}

export interface PoolSummary {
  total: number;
  active: number;
  eliminated: number;
  selected: string | null;
  can_undo: boolean;
  undo_depth: number;
}

export interface PreviewResult {
  visible: boolean;
  x: number;
  y: number;
  reason: string;
  borderline: boolean;
}

export interface PointPayload {
  visible: boolean;
  x: number;
  y: number;
  borderline: boolean;
  reason: string;
}

export interface AlignPayload {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface BonePoint {
  index: number;
  x: number;
  y: number;
}

export interface BoneFrame {
  points: BonePoint[];
  connections: [number, number][];
  /** 只显示这些序号的文本；为空表示全部 */
  label_only: number[];
  show_labels: boolean;
  show_lines: boolean;
  show_joints: boolean;
  /** label = 以「显示序号」为准；links = 以「连接关系」为准 */
  point_mode: string;
  font_size: number;
  font_color: string;
  line_color: string;
  line_width: number;
  point_radius: number;
  point_outline_width: number;
  point_color: string;
  visible_count: number;
}

export interface BoneConfigInput {
  base_address: string;
  count: number;
  stride: number;
  address: string;
  hidden: number[];
  connections: [number, number][];
  show_labels: boolean;
  show_lines: boolean;
  show_joints: boolean;
  point_mode: string;
  font_size: number;
  font_color: string;
  line_color: string;
  line_width: number;
  point_radius: number;
  point_outline_width: number;
  point_color: string;
  data_type: DataType;
  enabled: boolean;
}

export interface Settings {
  addresses: string;
  data_type: DataType;
  quadrant: Quadrant;
  world_x: number;
  world_y: number;
  world_z: number;
  size_w: number;
  size_h: number;
  /* 绘制 / 跟随频率（毫秒） */
  frame_follow_ms: number;
  frame_realtime_ms: number;
  frame_bone_ms: number;
  bone_base: string;
  bone_count: number;
  bone_stride: number;
  bone_addr: string;
  bone_hidden: string;
  bone_conn: string;
  bone_show_labels: boolean;
  bone_show_lines: boolean;
  bone_show_joints: boolean;
  bone_point_mode: string;
  bone_font_size: number;
  bone_font_color: string;
  bone_line_color: string;
  bone_line_width: number;
  bone_point_radius: number;
  bone_point_outline_width: number;
  bone_point_color: string;
  bone_enabled: boolean;
}

export interface AppInfo {
  name: string;
  version: string;
}

export interface AppError {
  code: string;
  message: string;
}

export const QUADRANTS: { id: Quadrant; label: string; hint: string }[] = [
  { id: "TL", label: "左上", hint: "TL" },
  { id: "TR", label: "右上", hint: "TR" },
  { id: "BL", label: "左下", hint: "BL" },
  { id: "BR", label: "右下", hint: "BR" },
];
