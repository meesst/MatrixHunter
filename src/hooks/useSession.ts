import { useCallback, useEffect, useRef, useState } from "react";
import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { api, errText, events } from "../lib/api";
import { parseConns, parseHidden } from "../lib/parse";
import { buildAlgoCode } from "../lib/exportAlgo";
import { urlOverride } from "../lib/prefs";
import type { BoneForm } from "../components/BonePanel";
import type { SettingsForm } from "../components/SettingsModal";
import type { StatusKind } from "../components/StatusBar";
import type {
  AppInfo,
  AttachInfo,
  DataType,
  PointPayload,
  ProcessInfo,
  Quadrant,
  SchemeView,
  Settings,
  WorldCoord,
} from "../types";

export const DEFAULT_BONE: BoneForm = {
  base: "",
  count: 0,
  stride: 16,
  addr: "",
  hidden: "",
  conn: "",
  showLabels: true,
  showLines: true,
  showJoints: true,
  pointMode: "label",
  fontSize: 13,
  fontColor: "#FFD54A",
  lineColor: "#35E0FF",
  lineWidth: 1.6,
  pointRadius: 3.2,
  pointOutlineWidth: 1.5,
  pointColor: "#35E0FF",
  enabled: false,
};

export const DEFAULT_SETTINGS_FORM: SettingsForm = {
  sizeW: 0,
  sizeH: 0,
  followMs: 16,
  realtimeMs: 25,
  boneMs: 70,
};

const EMPTY_SUMMARY = {
  total: 0,
  active: 0,
  eliminated: 0,
  selected: null as string | null,
  can_undo: false,
  undo_depth: 0,
};

function settingsFromState(p: {
  addresses: string;
  dataType: DataType;
  quadrant: Quadrant;
  world: WorldCoord;
  form: SettingsForm;
  bone: BoneForm;
}): Settings {
  return {
    addresses: p.addresses,
    data_type: p.dataType,
    quadrant: p.quadrant,
    world_x: p.world.x,
    world_y: p.world.y,
    world_z: p.world.z,
    size_w: p.form.sizeW,
    size_h: p.form.sizeH,
    frame_follow_ms: p.form.followMs,
    frame_realtime_ms: p.form.realtimeMs,
    frame_bone_ms: p.form.boneMs,
    bone_base: p.bone.base,
    bone_count: p.bone.count,
    bone_stride: p.bone.stride,
    bone_addr: p.bone.addr,
    bone_hidden: p.bone.hidden,
    bone_conn: p.bone.conn,
    bone_show_labels: p.bone.showLabels,
    bone_show_lines: p.bone.showLines,
    bone_show_joints: p.bone.showJoints,
    bone_point_mode: p.bone.pointMode,
    bone_font_size: p.bone.fontSize,
    bone_font_color: p.bone.fontColor,
    bone_line_color: p.bone.lineColor,
    bone_line_width: p.bone.lineWidth,
    bone_point_radius: p.bone.pointRadius,
    bone_point_outline_width: p.bone.pointOutlineWidth,
    bone_point_color: p.bone.pointColor,
    bone_enabled: p.bone.enabled,
  };
}

export function useSession(overlay: {
  showQuadrant: boolean;
  quadrantAlpha: number;
  quadrantLine: string;
  quadrantLineWidth: number;
}) {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const [loadingProc, setLoadingProc] = useState(false);
  const [attachInfo, setAttachInfo] = useState<AttachInfo | null>(null);

  const [addresses, setAddresses] = useState("");
  const [dataType, setDataType] = useState<DataType>("float");
  const [quadrant, setQuadrant] = useState<Quadrant>("TL");
  const [world, setWorld] = useState<WorldCoord>({ x: 0, y: 0, z: 0 });

  const [schemes, setSchemes] = useState<SchemeView[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 当前正在预览的方案 id（用于再次点击关闭预览）
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [summary, setSummary] = useState(EMPTY_SUMMARY);

  const [statusMsg, setStatusMsg] = useState("");
  const [statusKind, setStatusKind] = useState<StatusKind>("info");
  const [poolBusy, setPoolBusy] = useState(false);
  const [attachBusy, setAttachBusy] = useState(false);

  const [realtimeRunning, setRealtimeRunning] = useState(false);
  const [rtInfo, setRtInfo] = useState<PointPayload | null>(null);

  const [bone, setBone] = useState<BoneForm>(DEFAULT_BONE);
  const [boneLive, setBoneLive] = useState(0);

  const [settingsOpen, setSettingsOpen] = useState(() => urlOverride("settings") === "1");
  const [settingsForm, setSettingsForm] = useState<SettingsForm>(DEFAULT_SETTINGS_FORM);

  const setStatus = useCallback((kind: StatusKind, msg: string) => {
    setStatusKind(kind);
    setStatusMsg(msg);
  }, []);

  const refreshPool = useCallback(async () => {
    try {
      const [s, all] = await Promise.all([api.getPoolSummary(), api.getAllSchemes()]);
      setSummary(s);
      setSelectedId(s.selected);
      setSchemes(all);
    } catch (e) {
      setStatus("error", errText(e));
    }
  }, [setStatus]);

  const refreshProcesses = useCallback(async () => {
    setLoadingProc(true);
    try {
      const list = await api.listProcesses();
      setProcesses(list);
      setStatus("info", `已加载 ${list.length} 个进程`);
    } catch (e) {
      setStatus("error", errText(e));
    } finally {
      setLoadingProc(false);
    }
  }, [setStatus]);

  useEffect(() => {
    (async () => {
      try {
        setInfo(await api.appInfo());
      } catch {
        /* ignore */
      }
      try {
        const st: Settings = await api.loadSettings();
        setAddresses(st.addresses ?? "");
        setDataType((st.data_type as DataType) ?? "float");
        setQuadrant((st.quadrant as Quadrant) ?? "TL");
        setWorld({ x: st.world_x ?? 0, y: st.world_y ?? 0, z: st.world_z ?? 0 });
        setSettingsForm({
          sizeW: st.size_w ?? 0,
          sizeH: st.size_h ?? 0,
          followMs: st.frame_follow_ms ?? 16,
          realtimeMs: st.frame_realtime_ms ?? 25,
          boneMs: st.frame_bone_ms ?? 70,
        });
        setBone((b) => ({
          ...b,
          base: st.bone_base ?? "",
          count: st.bone_count ?? 0,
          stride: st.bone_stride ?? 16,
          addr: st.bone_addr ?? "",
          hidden: st.bone_hidden ?? "",
          conn: st.bone_conn ?? "",
          showLabels: st.bone_show_labels ?? true,
          showLines: st.bone_show_lines ?? true,
          showJoints: st.bone_show_joints ?? true,
          pointMode: st.bone_point_mode === "links" ? "links" : "label",
          fontSize: st.bone_font_size ?? 13,
          fontColor: st.bone_font_color ?? "#FFD54A",
          lineColor: st.bone_line_color ?? "#35E0FF",
          lineWidth: st.bone_line_width ?? 1.6,
          pointRadius: st.bone_point_radius ?? 3.2,
          pointOutlineWidth: st.bone_point_outline_width ?? 1.5,
          pointColor: st.bone_point_color ?? "#35E0FF",
          enabled: false,
        }));
        await api.setFrameConfig(
          st.frame_follow_ms ?? 16,
          st.frame_realtime_ms ?? 25,
          st.frame_bone_ms ?? 70
        );
        await api.setSizeOverride(st.size_w ?? 0, st.size_h ?? 0);
      } catch (e) {
        setStatus("error", errText(e));
      }
      await refreshProcesses();
      await refreshPool();
    })();
  }, [refreshProcesses, refreshPool, setStatus]);

  // 叠加层配置：缓存最新值，供 overlay 窗口就绪后重发。
  // 首次启动时 overlay 窗口可能还没挂载监听，事件会丢，导致十字线颜色 / 准星不生效。
  const overlayCfgRef = useRef({
    quadrant,
    showQuadrant: overlay.showQuadrant,
    quadrantAlpha: overlay.quadrantAlpha,
    quadrantLine: overlay.quadrantLine,
    quadrantLineWidth: overlay.quadrantLineWidth,
  });
  overlayCfgRef.current = {
    quadrant,
    showQuadrant: overlay.showQuadrant,
    quadrantAlpha: overlay.quadrantAlpha,
    quadrantLine: overlay.quadrantLine,
    quadrantLineWidth: overlay.quadrantLineWidth,
  };

  const pushOverlayCfg = useCallback(() => {
    const c = overlayCfgRef.current;
    emit("overlay:quadrant", {
      quadrant: c.quadrant,
      visible: c.showQuadrant,
      alpha: c.quadrantAlpha,
      line: c.quadrantLine,
      lineWidth: c.quadrantLineWidth,
    }).catch(() => {});
  }, []);

  useEffect(() => {
    pushOverlayCfg();
  }, [
    quadrant,
    overlay.showQuadrant,
    overlay.quadrantAlpha,
    overlay.quadrantLine,
    overlay.quadrantLineWidth,
    pushOverlayCfg,
  ]);

  // overlay 窗口每次加载完成会发 overlay:ready，此时补发一次当前配置。
  useEffect(() => {
    let un: (() => void) | undefined;
    let disposed = false;
    listen("overlay:ready", () => pushOverlayCfg())
      .then((u) => {
        if (disposed) u();
        else un = u;
      })
      .catch(() => {});
    return () => {
      disposed = true;
      un?.();
    };
  }, [pushOverlayCfg]);

  useEffect(() => {
    api.stopPreview().catch(() => {});
    setPreviewId(null);
    // 仅在挂载时清理一次可能残留的预览
  }, []);

  // 世界坐标变化时同步给后端：实时点与预览都用它作为投影输入。
  useEffect(() => {
    const t = setTimeout(() => {
      api.setWorld(world.x, world.y, world.z).catch(() => {});
    }, 180);
    return () => clearTimeout(t);
  }, [world]);

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .setBoneConfig({
          base_address: bone.base,
          count: bone.count,
          stride: bone.stride,
          address: bone.addr,
          hidden: parseHidden(bone.hidden),
          connections: parseConns(bone.conn),
          show_labels: bone.showLabels,
          show_lines: bone.showLines,
          show_joints: bone.showJoints,
          point_mode: bone.pointMode,
          font_size: bone.fontSize,
          font_color: bone.fontColor,
          line_color: bone.lineColor,
          line_width: bone.lineWidth,
          point_radius: bone.pointRadius,
          point_outline_width: bone.pointOutlineWidth,
          point_color: bone.pointColor,
          data_type: dataType,
          enabled: bone.enabled,
        })
        .catch(() => {});
    }, 220);
    return () => clearTimeout(t);
  }, [bone, dataType]);

  const attachPidRef = useRef<(pid: number, name?: string) => Promise<void>>(async () => {});

  const attachPid = useCallback(
    async (pid: number, name?: string) => {
      try {
        setAttachBusy(true);
        const a = await api.attachProcess(pid);
        setAttachInfo(a);
        setStatus(
          "ok",
          `已附加 ${name ?? a.name} (pid ${a.pid})` +
            (a.hwnd_found
              ? ` · 客户区 ${a.client_w}×${a.client_h}`
              : " · 未找到可见窗口（叠加层不会显示）")
        );
        await refreshPool();
      } catch (e) {
        setStatus("error", errText(e));
      } finally {
        setAttachBusy(false);
      }
    },
    [refreshPool, setStatus]
  );

  attachPidRef.current = attachPid;

  useEffect(() => {
    const uns: Array<() => void> = [];
    (async () => {
      uns.push(await events.onRealtimePoint((p) => setRtInfo(p)));
      uns.push(await events.onBoneFrame((f) => setBoneLive(f.visible_count)));
      uns.push(
        await events.onPickDone(async (r) => {
          getCurrentWindow().show().catch(() => {});
          if (r.ok) await attachPidRef.current(r.pid, r.name);
          else setStatus("warn", r.reason || "未选中窗口");
        })
      );
    })();
    return () => {
      for (const u of uns) u();
    };
  }, [setStatus]);

  const handleDetach = useCallback(async () => {
    try {
      await api.detachProcess();
      setAttachInfo(null);
      setRealtimeRunning(false);
      setRtInfo(null);
      setBoneLive(0);
      await refreshPool();
      setStatus("info", "已断开目标进程");
    } catch (e) {
      setStatus("error", errText(e));
    }
  }, [refreshPool, setStatus]);

  const handleEnumerate = useCallback(async () => {
    const list = addresses
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (list.length === 0) {
      setStatus("warn", "请先输入至少一个地址");
      return;
    }
    try {
      setPoolBusy(true);
      const res = await api.enumerate(list, dataType);
      await refreshPool();
      setStatus(
        "ok",
        `枚举完成：${res.total} 个方案` +
          (res.invalid.length ? ` · ${res.invalid.length} 个地址无效已忽略` : "")
      );
    } catch (e) {
      setStatus("error", errText(e));
    } finally {
      setPoolBusy(false);
    }
  }, [addresses, dataType, refreshPool, setStatus]);

  const handleFilter = useCallback(async () => {
    try {
      setPoolBusy(true);
      const o = await api.filter(quadrant, world);
      await refreshPool();
      if (o.auto_rolled_back) {
        setStatus(
          "warn",
          `本轮无方案存活（${o.before_count} → 0），已自动回滚。请调整象限或世界坐标。`
        );
      } else {
        setStatus(
          "ok",
          `过滤完成：${o.before_count} → ${o.after_count}（淘汰 ${o.eliminated_ids.length}${
            o.skipped_ids.length
              ? `，读取失败保留 ${o.skipped_ids.length}（再过滤一次仍失败将被剔除）`
              : ""
          }）`
        );
      }
    } catch (e) {
      setStatus("error", errText(e));
    } finally {
      setPoolBusy(false);
    }
  }, [quadrant, world, refreshPool, setStatus]);

  const doUndo = useCallback(async () => {
    try {
      const n = await api.undoFilter();
      await refreshPool();
      setStatus(n == null ? "info" : "ok", n == null ? "没有可撤销的操作" : `已撤销，恢复 ${n} 个方案`);
    } catch (e) {
      setStatus("error", errText(e));
    }
  }, [refreshPool, setStatus]);

  const handleReset = useCallback(async () => {
    try {
      await api.resetPool();
      await refreshPool();
      setStatus("info", "已清空方案池");
    } catch (e) {
      setStatus("error", errText(e));
    }
  }, [refreshPool, setStatus]);

  const handleSelect = useCallback(
    async (id: string) => {
      try {
        await api.selectScheme(id);
        await refreshPool();
        setStatus("ok", "已选中方案");
      } catch (e) {
        setStatus("error", errText(e));
      }
    },
    [refreshPool, setStatus]
  );

  /** 「实时预览」：选中并开启实时；对同一条再次点击则停止。 */
  const handleRealtimePreview = useCallback(
    async (id: string) => {
      try {
        if (selectedId === id && realtimeRunning) {
          await api.stopRealtime();
          setRealtimeRunning(false);
          setStatus("info", "实时追踪：关闭");
          return;
        }
        await api.selectScheme(id);
        await api.startRealtime();
        setRealtimeRunning(true);
        await refreshPool();
        setStatus("ok", "已选中并开启实时追踪");
      } catch (e) {
        setStatus("error", errText(e));
      }
    },
    [selectedId, realtimeRunning, refreshPool, setStatus]
  );

  const handleRemove = useCallback(
    async (id: string) => {
      try {
        await api.removeScheme(id);
        await refreshPool();
      } catch (e) {
        setStatus("error", errText(e));
      }
    },
    [refreshPool]
  );

  const handlePreview = useCallback(
    async (id: string) => {
      // 再次点击同一条方案 → 关闭预览，叠加层上的预览点会随之清除
      if (previewId === id) {
        try {
          await api.stopPreview();
        } catch {
          /* ignore */
        }
        setPreviewId(null);
        setStatus("info", "已关闭预览");
        return;
      }
      try {
        const r = await api.previewScheme(id);
        setPreviewId(id);
        setStatus(
          r.visible ? "ok" : "warn",
          r.visible
            ? `预览点：(${r.x.toFixed(1)}, ${r.y.toFixed(1)})${r.borderline ? " · 近边界" : ""}（再次点该按钮可关闭）`
            : `预览不可见：${r.reason}`
        );
      } catch (e) {
        setStatus("error", errText(e));
      }
    },
    [previewId, setStatus]
  );

  const handleCopy = useCallback(
    (addr: string) => {
      navigator.clipboard?.writeText(addr).then(
        () => setStatus("ok", `已复制 ${addr}`),
        () => setStatus("warn", "复制失败")
      );
    },
    [setStatus]
  );

  /** 导出该方案的整套「世界 → 屏幕」算法代码（含读矩阵、运算、比例换算）到剪贴板。 */
  const handleCopyAlgo = useCallback(
    (id: string) => {
      const s = schemes.find((x) => x.scheme_id === id);
      if (!s) return;
      const cw = settingsForm.sizeW > 0 ? settingsForm.sizeW : attachInfo?.client_w ?? 0;
      const ch = settingsForm.sizeH > 0 ? settingsForm.sizeH : attachInfo?.client_h ?? 0;
      const code = buildAlgoCode(s, {
        clientW: cw,
        clientH: ch,
        clientX: attachInfo?.client_x ?? 0,
        clientY: attachInfo?.client_y ?? 0,
        screenW: cw,
        screenH: ch,
      });
      navigator.clipboard?.writeText(code).then(
        () => setStatus("ok", "已复制该方案的算法代码（C++）到剪贴板"),
        () => setStatus("warn", "复制失败")
      );
    },
    [schemes, settingsForm.sizeW, settingsForm.sizeH, attachInfo, setStatus]
  );

  const toggleRealtime = useCallback(async () => {
    try {
      if (realtimeRunning) {
        await api.stopRealtime();
        setRealtimeRunning(false);
        setStatus("info", "实时追踪：关闭");
      } else {
        await api.startRealtime();
        setRealtimeRunning(true);
        setStatus("ok", "实时追踪：开启（按左侧填写的世界坐标投影）");
      }
    } catch (e) {
      setStatus("error", errText(e));
    }
  }, [realtimeRunning, setStatus]);

  const handleBoneFilter = useCallback(async () => {
    try {
      setPoolBusy(true);
      const o = await api.boneApplyFilter(quadrant);
      await refreshPool();
      setStatus(
        o.auto_rolled_back ? "warn" : "ok",
        o.auto_rolled_back
          ? "骨骼过滤：无方案存活，已自动回滚"
          : `骨骼过滤：${o.before_count} → ${o.after_count}`
      );
    } catch (e) {
      setStatus("error", errText(e));
    } finally {
      setPoolBusy(false);
    }
  }, [quadrant, refreshPool, setStatus]);

  const beginDragPick = useCallback(async () => {
    try {
      await getCurrentWindow().hide();
    } catch {
      /* ignore */
    }
    await new Promise((r) => setTimeout(r, 60));
    api.startPick().catch((e) => {
      getCurrentWindow().show().catch(() => {});
      setStatus("error", errText(e));
    });
  }, [setStatus]);

  const saveSettings = useCallback(
    async (v: SettingsForm) => {
      setSettingsOpen(false);
      setSettingsForm(v);
      try {
        await api.setFrameConfig(v.followMs, v.realtimeMs, v.boneMs);
        await api.setSizeOverride(v.sizeW, v.sizeH);
        await api.refreshTargetWindow().then((a) => a && setAttachInfo(a));
        await api.saveSettings(
          settingsFromState({ addresses, dataType, quadrant, world, form: v, bone })
        );
        setStatus("ok", "设置已保存");
      } catch (e) {
        setStatus("error", errText(e));
      }
    },
    [addresses, dataType, quadrant, world, bone, setStatus]
  );

  return {
    info,
    processes,
    loadingProc,
    attachInfo,
    attached: !!attachInfo,
    addresses,
    setAddresses,
    dataType,
    setDataType,
    quadrant,
    setQuadrant,
    world,
    setWorld,
    schemes,
    selectedId,
    previewId,
    summary,
    statusMsg,
    statusKind,
    poolBusy,
    attachBusy,
    realtimeRunning,
    rtInfo,
    bone,
    setBone,
    boneLive,
    settingsOpen,
    setSettingsOpen,
    settingsForm,
    refreshProcesses,
    attachPid,
    handleDetach,
    handleEnumerate,
    handleFilter,
    doUndo,
    handleReset,
    handleSelect,
    handleRealtimePreview,
    handleRemove,
    handlePreview,
    handleCopy,
    handleCopyAlgo,
    toggleRealtime,
    handleBoneFilter,
    beginDragPick,
    saveSettings,
  };
}
