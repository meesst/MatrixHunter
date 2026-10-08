import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Tauri 期望固定端口
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      // 不监听 rust 源码
      ignored: ["**/src-tauri/**"],
    },
  },
  build: {
    // Windows WebView2 基于 Chromium，可用较新语法
    target: "chrome105",
    minify: "esbuild",
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
  },
});
