import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import ProcessPanel from "./ProcessPanel";
import FindPanel from "./FindPanel";
import BonePanel from "./BonePanel";
import ResultTable from "./ResultTable";
import WindowInfoPanel from "./WindowInfoPanel";
import StatusBar from "./StatusBar";
import SettingsModal from "./SettingsModal";
import TitleBar from "./TitleBar";
import TooltipLayer from "./TooltipLayer";
import { TIPS } from "../lib/tips";
import { urlOverride } from "../lib/prefs";
import { useAppearance } from "../hooks/useAppearance";
import { useSession } from "../hooks/useSession";

type TabKey = "proc" | "find" | "bone";
const TAB_ORDER: TabKey[] = ["proc", "find", "bone"];
const TAB_LABELS: Record<TabKey, string> = {
  proc: "目标进程",
  find: "矩阵查找",
  bone: "骨骼编号",
};
const TAB_TIPS: Record<TabKey, string> = {
  proc: TIPS.tabs.proc,
  find: TIPS.tabs.find,
  bone: TIPS.tabs.bone,
};

export default function MainUI() {
  const appearance = useAppearance();
  const session = useSession({
    showQuadrant: appearance.showQuadrant,
    quadrantAlpha: appearance.quadrantAlpha,
    quadrantLine: appearance.quadrantLine,
    quadrantLineWidth: appearance.quadrantLineWidth,
  });

  const [leftTab, setLeftTab] = useState<TabKey>(() => {
    const v = urlOverride("tab");
    return v === "find" || v === "bone" ? v : "proc";
  });
  const [tabDir, setTabDir] = useState<1 | -1>(1);
  const tabsRef = useRef<HTMLDivElement | null>(null);
  const tabBtnRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [ind, setInd] = useState({ x: 0, w: 0, ready: false });
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);

  const changeTab = useCallback(
    (k: TabKey) => {
      setTabDir(TAB_ORDER.indexOf(k) > TAB_ORDER.indexOf(leftTab) ? 1 : -1);
      setLeftTab(k);
    },
    [leftTab]
  );

  useLayoutEffect(() => {
    const measure = () => {
      const wrap = tabsRef.current;
      const el = tabBtnRefs.current[leftTab];
      if (!wrap || !el) return;
      const wr = wrap.getBoundingClientRect();
      const er = el.getBoundingClientRect();
      setInd({ x: er.left - wr.left, w: er.width, ready: true });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
    // leadW 变化（拖动分隔条）会改变左栏宽度，需要重新测量指示器位置
  }, [leftTab, appearance.leadW]);

  const onSplitDown = (e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startW: appearance.leadW };
    const onMove = (ev: globalThis.MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      appearance.setLeadW(Math.min(560, Math.max(280, d.startW + (ev.clientX - d.startX))));
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const selectedAddr = useMemo(
    () => session.schemes.find((s) => s.scheme_id === session.selectedId)?.address_hex ?? "",
    [session.schemes, session.selectedId]
  );

  const attached = session.attached;
  const attachInfo = session.attachInfo;
  const banner =
    !attached
      ? "未附加进程 · 先在「目标进程」附加后再枚举"
      : attachInfo && !attachInfo.hwnd_found
        ? "已附加，但未找到可见窗口 · 叠加层不会显示"
        : session.statusKind === "warn"
          ? session.statusMsg
          : null;

  return (
    <div className="app" data-layout="c">
      <TitleBar
        version={session.info?.version}
        attached={attached}
        attachLabel={
          attached && attachInfo ? `${attachInfo.name} · ${attachInfo.pid}` : undefined
        }
        onOpenSettings={() => session.setSettingsOpen(true)}
      />

      <div className="main layout-c">
        <div className="col col-lead" data-dir={tabDir === 1 ? "right" : "left"}>
          <div className="tabs" ref={tabsRef}>
            <div
              className={`tab-indicator${ind.ready ? "" : " no-anim"}`}
              style={{ transform: `translateX(${ind.x}px)`, width: ind.w }}
            >
              <div className="tab-indicator-fill" key={leftTab} />
            </div>
            {TAB_ORDER.map((k) => (
              <button
                key={k}
                ref={(el) => {
                  tabBtnRefs.current[k] = el;
                }}
                className={`tab ${leftTab === k ? "active" : ""}`}
                onClick={() => changeTab(k)}
                data-tip={TAB_TIPS[k]}
              >
                {TAB_LABELS[k]}
              </button>
            ))}
          </div>
          {leftTab === "proc" && (
            <ProcessPanel
              processes={session.processes}
              attached={session.attachInfo}
              loading={session.loadingProc}
              onRefresh={session.refreshProcesses}
              onAttach={(pid) => session.attachPid(pid)}
              onDetach={session.handleDetach}
              onPickWindow={session.beginDragPick}
            />
          )}
          {leftTab === "find" && (
            <FindPanel
              addresses={session.addresses}
              setAddresses={session.setAddresses}
              dataType={session.dataType}
              setDataType={session.setDataType}
              quadrant={session.quadrant}
              setQuadrant={session.setQuadrant}
              world={session.world}
              setWorld={session.setWorld}
              onEnumerate={session.handleEnumerate}
              onFilter={session.handleFilter}
              onUndo={session.doUndo}
              onReset={session.handleReset}
              onLoadFileText={(t) =>
                session.setAddresses((prev) => (prev.trim() ? prev.trimEnd() + "\n" + t : t))
              }
              canUndo={session.summary.can_undo}
              busy={session.poolBusy}
              attached={attached}
              schemeCount={session.summary.total}
            />
          )}
          {leftTab === "bone" && (
            <BonePanel
              value={session.bone}
              onChange={(p) => session.setBone((b) => ({ ...b, ...p }))}
              liveCount={session.boneLive}
              hasSelection={!!session.summary.selected}
              schemeAddress={selectedAddr}
            />
          )}
        </div>

        <div className="split" onMouseDown={onSplitDown} data-tip="拖动调整左栏宽度" />

        <div className="col col-body">
          {leftTab === "proc" ? (
            <WindowInfoPanel attachInfo={attachInfo} />
          ) : (
            <div className="card" style={{ flex: 1, minHeight: 0 }}>
              <ResultTable
                schemes={session.schemes}
                selectedId={session.selectedId}
                previewId={session.previewId}
                realtimeRunning={session.realtimeRunning}
                banner={banner}
                bannerKind={
                  !attached || (attachInfo && !attachInfo.hwnd_found)
                    ? "warn"
                    : session.statusKind === "warn"
                      ? "warn"
                      : "info"
                }
                onSelect={session.handleSelect}
                onPreview={session.handlePreview}
                onRealtimePreview={session.handleRealtimePreview}
                onRemove={session.handleRemove}
                onCopy={session.handleCopy}
                onCopyAlgo={session.handleCopyAlgo}
              />
            </div>
          )}
        </div>
      </div>

      <StatusBar
        message={
          session.rtInfo
            ? session.rtInfo.visible
              ? `${session.statusMsg} · 实时点 (${session.rtInfo.x.toFixed(1)}, ${session.rtInfo.y.toFixed(1)})${
                  session.rtInfo.borderline ? " 近边界" : ""
                }`
              : session.statusMsg
            : session.statusMsg
        }
        kind={session.statusKind}
        summary={session.summary}
        realtimeRunning={session.realtimeRunning}
        attached={attached}
      />

      <SettingsModal
        open={session.settingsOpen}
        value={session.settingsForm}
        onClose={() => session.setSettingsOpen(false)}
        onSave={session.saveSettings}
        themeMode={appearance.themeMode}
        accent={appearance.accent}
        onTheme={appearance.setThemeMode}
        onAccent={appearance.setAccent}
        showQuadrant={appearance.showQuadrant}
        onShowQuadrant={appearance.setShowQuadrant}
        quadrantAlpha={appearance.quadrantAlpha}
        onQuadrantAlpha={appearance.setQuadrantAlpha}
        quadrantLine={appearance.quadrantLine}
        onQuadrantLine={appearance.setQuadrantLine}
        quadrantLineWidth={appearance.quadrantLineWidth}
        onQuadrantLineWidth={appearance.setQuadrantLineWidth}
      />

      <TooltipLayer />
    </div>
  );
}
