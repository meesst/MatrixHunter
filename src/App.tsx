import { getCurrentWindow } from "@tauri-apps/api/window";
import MainUI from "./components/MainUI";
import Overlay from "./components/Overlay";
import Picker from "./components/Picker";
import { isTauri } from "./lib/env";

export default function App() {
  // 浏览器直开（本地 UI 调试）时无 Tauri 容器，直接渲染主界面。
  if (!isTauri) return <MainUI />;

  const label = getCurrentWindow().label;
  if (label === "overlay") return <Overlay />;
  if (label === "picker") return <Picker />;
  return <MainUI />;
}
