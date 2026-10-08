/** 判断当前是否运行在 Tauri 容器内（浏览器直开时为 false，用于本地 UI 预览）。 */
export const isTauri: boolean =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
