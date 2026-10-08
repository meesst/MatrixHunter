import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { isTauri } from "./env";
import { mockInvoke } from "../dev/mock";
import type {
  AppError,
  AppInfo,
  AttachInfo,
  BoneConfigInput,
  BoneFrame,
  DataType,
  EnumerateResult,
  FilterOutcome,
  PoolSummary,
  PreviewResult,
  PickDone,
  PickHover,
  PointPayload,
  ProcessInfo,
  Quadrant,
  SchemeView,
  Settings,
  WorldCoord,
  WindowUnderCursor,
  WindowDetail,
  PerfSnapshot,
  AlignPayload,
} from "../types";

async function call<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri) return mockInvoke<T>(cmd, args);
  try {
    return await invoke<T>(cmd, args);
  } catch (e: any) {
    if (e && typeof e === "object" && "message" in e) {
      throw e as AppError;
    }
    throw { code: "ERROR", message: String(e) } as AppError;
  }
}

export const api = {
  listProcesses: () => call<ProcessInfo[]>("list_processes"),
  attachProcess: (pid: number) => call<AttachInfo>("attach_process", { pid }),
  detachProcess: () => call<void>("detach_process"),
  windowUnderCursor: () => call<WindowUnderCursor>("window_under_cursor"),
  startPick: () => call<void>("start_pick"),
  refreshTargetWindow: () => call<AttachInfo | null>("refresh_target_window"),
  windowDetail: () => call<WindowDetail | null>("window_detail"),
  perfSnapshot: () => call<PerfSnapshot>("perf_snapshot"),
  setSizeOverride: (width: number, height: number) =>
    call<void>("set_size_override", { width, height }),

  enumerate: (addresses: string[], dataType: DataType) =>
    call<EnumerateResult>("enumerate", { addresses, dataType }),
  filter: (quadrant: Quadrant, world: WorldCoord) =>
    call<FilterOutcome>("filter", { quadrant, world }),
  boneApplyFilter: (quadrant: Quadrant) =>
    call<FilterOutcome>("bone_apply_filter", { quadrant }),
  undoFilter: () => call<number | null>("undo_filter"),
  resetPool: () => call<void>("reset_pool"),
  removeScheme: (schemeId: string) => call<boolean>("remove_scheme", { schemeId }),
  selectScheme: (schemeId: string) => call<boolean>("select_scheme", { schemeId }),
  getPoolSummary: () => call<PoolSummary>("get_pool_summary"),
  getActiveSchemes: () => call<SchemeView[]>("get_active_schemes"),
  getAllSchemes: () => call<SchemeView[]>("get_all_schemes"),

  previewScheme: (schemeId: string) => call<PreviewResult>("preview_scheme", { schemeId }),
  stopPreview: () => call<void>("stop_preview"),

  startRealtime: () => call<void>("start_realtime"),
  stopRealtime: () => call<void>("stop_realtime"),
  setWorld: (x: number, y: number, z: number) => call<void>("set_world", { x, y, z }),
  setBoneConfig: (config: BoneConfigInput) => call<void>("set_bone_config", { config }),
  setFrameConfig: (followMs: number, realtimeMs: number, boneMs: number) =>
    call<void>("set_frame_config", {
      followMs,
      realtimeMs,
      boneMs,
    }),

  appInfo: () => call<AppInfo>("app_info"),
  readAddress: (address: string, dataType: DataType) =>
    call<number[]>("read_address", { address, dataType }),

  saveSettings: (settings: Settings) => call<void>("save_settings", { settings }),
  loadSettings: () => call<Settings>("load_settings"),
};

const noopUnlisten: () => void = () => {};

/** 真实环境走 Tauri 事件；浏览器预览时返回空订阅，保证组件不报错。 */
function sub<T>(name: string, cb: (payload: T) => void): Promise<UnlistenFn> {
  if (!isTauri) return Promise.resolve(noopUnlisten);
  return listen<T>(name, (e) => cb(e.payload));
}

export const events = {
  onRealtimePoint: (cb: (p: PointPayload) => void): Promise<UnlistenFn> =>
    sub<PointPayload>("realtime:point", cb),
  onOverlayPreview: (cb: (p: PreviewResult) => void): Promise<UnlistenFn> =>
    sub<PreviewResult>("overlay:preview", cb),
  onBoneFrame: (cb: (f: BoneFrame) => void): Promise<UnlistenFn> =>
    sub<BoneFrame>("bone:frame", cb),
  onOverlayAlign: (cb: (a: AlignPayload) => void): Promise<UnlistenFn> =>
    sub<AlignPayload>("overlay:align", cb),
  onPickHover: (cb: (p: PickHover) => void): Promise<UnlistenFn> =>
    sub<PickHover>("pick:hover", cb),
  onPickDone: (cb: (p: PickDone) => void): Promise<UnlistenFn> =>
    sub<PickDone>("pick:done", cb),
};

export function errText(e: unknown): string {
  if (e && typeof e === "object" && "message" in (e as any)) {
    return String((e as AppError).message);
  }
  return String(e);
}
