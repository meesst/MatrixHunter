/**
 * 仅用于浏览器直开预览 UI 的假数据层（Tauri 真机环境不会走到这里）。
 * 目的：在没有 Rust 后端时也能渲染出完整界面用于视觉调试 / 截图。
 */
import type {
  AppInfo,
  AttachInfo,
  FilterOutcome,
  PoolSummary,
  PreviewResult,
  ProcessInfo,
  SchemeView,
  Settings,
  WindowUnderCursor,
} from "../types";

const PROCESSES: ProcessInfo[] = [
  { pid: 4821, name: "chrome.exe", is_64bit: true },
  { pid: 9136, name: "Code.exe", is_64bit: true },
  { pid: 3312, name: "explorer.exe", is_64bit: true },
  { pid: 7745, name: "notepad.exe", is_64bit: false },
  { pid: 1180, name: "MatrixHunter.exe", is_64bit: true },
  { pid: 6620, name: "Terminal.exe", is_64bit: true },
  { pid: 2044, name: "msedge.exe", is_64bit: true },
  { pid: 8807, name: "Taskmgr.exe", is_64bit: true },
];

const SCHEMES: SchemeView[] = [
  {
    scheme_id: "s1",
    address: 0x7ff6a1b2c3d0,
    address_hex: "0x7FF6A1B2C3D0",
    description: "矩阵候选 · 行主序",
    data_type: "float",
    shape: "4x4",
    layout: "row-major",
    mul_direction: "left",
    clip_w_sign: "positive",
    status: "active",
  },
  {
    scheme_id: "s2",
    address: 0x7ff6a1b2d180,
    address_hex: "0x7FF6A1B2D180",
    description: "矩阵候选 · 列主序",
    data_type: "float",
    shape: "4x4",
    layout: "column-major",
    mul_direction: "right",
    clip_w_sign: "positive",
    status: "active",
  },
  {
    scheme_id: "s3",
    address: 0x14c3d0a0,
    address_hex: "0x14C3D0A0",
    description: "矩阵候选 · 透视投影",
    data_type: "double",
    shape: "4x4",
    layout: "row-major",
    mul_direction: "left",
    clip_w_sign: "negative",
    status: "active",
  },
  {
    scheme_id: "s4",
    address: 0x14c3d240,
    address_hex: "0x14C3D240",
    description: "矩阵候选 · 正交投影",
    data_type: "float",
    shape: "3x3",
    layout: "row-major",
    mul_direction: "left",
    clip_w_sign: "positive",
    status: "eliminated" as unknown as SchemeView["status"],
  },
];

const SETTINGS: Settings = {
  addresses: "0x7FF6A1B2C3D0\n0x7FF6A1B2D180\n0x14C3D0A0\n0x14C3D240",
  data_type: "float",
  quadrant: "TL",
  world_x: 128.5,
  world_y: 64.25,
  world_z: -12,
  size_w: 0,
  size_h: 0,
  frame_follow_ms: 16,
  frame_realtime_ms: 25,
  frame_bone_ms: 70,
  bone_base: "0x21F4A0C0",
  bone_count: 32,
  bone_stride: 16,
  bone_addr: "0x7FF6A1B2C3D0",
  bone_hidden: "3,7,12",
  bone_conn: "0-1\n1-2\n2-3\n3-4",
  bone_font_size: 13,
  bone_font_color: "#FFD54A",
  bone_line_color: "#35E0FF",
  bone_line_width: 1.6,
  bone_point_radius: 3.2,
  bone_point_color: "#35E0FF",
  bone_enabled: false,
};

let attached: AttachInfo | null = null;

const ATTACH: AttachInfo = {
  pid: 4821,
  name: "chrome.exe",
  hwnd_found: true,
  client_x: 0,
  client_y: 0,
  client_w: 1920,
  client_h: 1080,
};

function summary(): PoolSummary {
  return {
    total: SCHEMES.length,
    active: SCHEMES.filter((s) => s.status === "active").length,
    eliminated: SCHEMES.filter((s) => s.status !== "active").length,
    selected: "s1",
    can_undo: true,
    undo_depth: 2,
  };
}

export async function mockInvoke<T>(cmd: string, _args?: Record<string, unknown>): Promise<T> {
  await new Promise((r) => setTimeout(r, 30));
  switch (cmd) {
    case "app_info":
      return { name: "MatrixHunter", version: "1.0.0" } as AppInfo as T;
    case "list_processes":
      return PROCESSES as unknown as T;
    case "attach_process":
      attached = ATTACH;
      return ATTACH as unknown as T;
    case "detach_process":
      attached = null;
      return undefined as unknown as T;
    case "refresh_target_window":
      return attached as unknown as T;
    case "window_under_cursor":
      return {
        pid: 4821,
        name: "chrome.exe",
        title: "目标窗口",
        class_name: "Chrome_WidgetWin_1",
        hwnd_found: true,
      } as WindowUnderCursor as T;
    case "get_pool_summary":
      return summary() as unknown as T;
    case "get_all_schemes":
      return SCHEMES as unknown as T;
    case "get_active_schemes":
      return SCHEMES.filter((s) => s.status === "active") as unknown as T;
    case "preview_scheme":
      return {
        visible: true,
        x: 842.5,
        y: 396.2,
        reason: "",
        borderline: false,
      } as PreviewResult as T;
    case "filter":
    case "bone_apply_filter":
      return {
        before_count: 4,
        after_count: 3,
        eliminated_ids: ["s4"],
        skipped_ids: [],
        auto_rolled_back: false,
      } as FilterOutcome as T;
    case "undo_filter":
      return 1 as unknown as T;
    case "enumerate":
      return { schemes: SCHEMES, invalid: [], total: SCHEMES.length } as unknown as T;
    case "load_settings":
      return SETTINGS as unknown as T;
    default:
      return undefined as unknown as T;
  }
}
