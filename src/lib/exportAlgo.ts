import type { SchemeView } from "../types";

export interface AlgoEnv {
  /** 目标客户区尺寸与左上角屏幕坐标 */
  clientW: number;
  clientH: number;
  clientX: number;
  clientY: number;
  /** 叠加层 / 绘制区尺寸（一般与客户区一致） */
  screenW: number;
  screenH: number;
}

/**
 * 把一条方案整理成一套可直接使用的 C++ 实现：
 * 读取矩阵地址 → 按布局/形状构建矩阵 → 按方向/符号做投影 → 世界坐标转屏幕坐标。
 * 常量部分预留了世界坐标、窗口信息、矩阵地址，填好即可运行。
 */
export function buildAlgoCode(s: SchemeView, env: AlgoEnv): string {
  const isFloat = s.data_type === "float";
  const elemBytes = isFloat ? 4 : 8;
  const is4x4 = s.shape === "4x4";
  const elemCount = is4x4 ? 16 : 12;
  const rowMajor = s.layout === "row_major";
  const vecMulM = s.mul_direction === "v*M";
  const positive = s.clip_w_sign === "+w";

  const buildMatrixBody = is4x4
    ? rowMajor
      ? `    // 4x4 行主序：m[i][j] = raw[i*4 + j]
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 4; j++)
            m[i][j] = raw[i * 4 + j];`
      : `    // 4x4 列主序：m[i][j] = raw[j*4 + i]
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 4; j++)
            m[i][j] = raw[j * 4 + i];`
    : `    // 3x4：前三行取自 raw，最后一行补 [0,0,0,1]
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 4; j++)
            m[i][j] = raw[i * 4 + j];
    m[3][0] = 0.0; m[3][1] = 0.0; m[3][2] = 0.0; m[3][3] = 1.0;`;

  const mulBody = vecMulM
    ? `    // v*M：行向量乘矩阵  t[j] = Σ_i v[i] * m[i][j]
    for (int j = 0; j < 4; j++) {
        double sum = 0.0;
        for (int i = 0; i < 4; i++) sum += v[i] * m[i][j];
        t[j] = sum;
    }`
    : `    // M*v：矩阵乘列向量  t[i] = Σ_j m[i][j] * v[j]
    for (int i = 0; i < 4; i++) {
        double sum = 0.0;
        for (int j = 0; j < 4; j++) sum += m[i][j] * v[j];
        t[i] = sum;
    }`;

  return `// ============================================================
// MatrixHunter 导出：世界坐标 -> 屏幕坐标
// 方案：${s.description}（${s.data_type}）
// 地址：${s.address_hex}
// ------------------------------------------------------------
// 依赖 Windows（ReadProcessMemory）。填好下面的常量、传入
// PROCESS_VM_READ 权限的 hProcess 即可调用。
// ============================================================
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <cstdio>

// ---------------- 需要你填写 / 替换的常量 ----------------
static const uintptr_t MATRIX_ADDRESS = ${s.address_hex};  // 矩阵地址
static const int  ELEMENT_BYTES = ${elemBytes};   // ${s.data_type}：4=float, 8=double
static const int  ELEMENT_COUNT = ${elemCount};   // ${s.shape}
static const int  CLIENT_WIDTH  = ${env.clientW};  // 目标客户区宽度（像素）
static const int  CLIENT_HEIGHT = ${env.clientH};  // 目标客户区高度（像素）
static const int  CLIENT_X      = ${env.clientX};  // 客户区左上角屏幕 X
static const int  CLIENT_Y      = ${env.clientY};  // 客户区左上角屏幕 Y
static const int  SCREEN_WIDTH  = ${env.screenW};  // 叠加层 / 绘制区宽度（一般 = 客户区宽）
static const int  SCREEN_HEIGHT = ${env.screenH};  // 叠加层 / 绘制区高度（一般 = 客户区高）

// ---------------- 读取矩阵原始数据 ----------------
static bool ReadMatrix(HANDLE hProcess, double raw[16]) {
    const SIZE_T bytes = (SIZE_T)ELEMENT_COUNT * ELEMENT_BYTES;
    unsigned char buf[16 * 8];
    SIZE_T read = 0;
    if (!ReadProcessMemory(hProcess, (LPCVOID)MATRIX_ADDRESS, buf, bytes, &read)) return false;
    if (read != bytes) return false;
    for (int i = 0; i < ELEMENT_COUNT; i++) {
        if (ELEMENT_BYTES == 4) { float f; memcpy(&f, buf + i * 4, 4); raw[i] = (double)f; }
        else                    { double d; memcpy(&d, buf + i * 8, 8); raw[i] = d; }
    }
    return true;
}

// ---------------- 构建 4x4 矩阵 ----------------
// 形状 ${s.shape} / 布局 ${s.layout}
static void BuildMatrix(const double raw[16], double m[4][4]) {
${buildMatrixBody}
}

// ---------------- 世界坐标 -> 屏幕坐标 ----------------
// 乘法方向 ${s.mul_direction} / clip-w 符号 ${s.clip_w_sign}
static bool WorldToScreen(HANDLE hProcess, double wx, double wy, double wz,
                          double* outX, double* outY) {
    double raw[16] = {0};
    if (!ReadMatrix(hProcess, raw)) return false;

    double m[4][4];
    BuildMatrix(raw, m);

    double v[4] = { wx, wy, wz, 1.0 };
    double t[4] = { 0, 0, 0, 0 };
${mulBody}

    double w = ${positive ? "t[3]" : "-t[3]"};   // clip-w
    if (w <= 1e-6) return false;        // 位于相机后方
    if (w > 1e7)  return false;         // 数值异常

    double ndcX = t[0] / w;
    double ndcY = t[1] / w;

    // NDC [-1,1] -> 屏幕比例 [0,1]（Y 轴向下）
    double clipX = ndcX * 0.5 + 0.5;
    double clipY = 1.0 - (ndcY * 0.5 + 0.5);

    if (clipX < 0.0 || clipX > 1.0 || clipY < 0.0 || clipY > 1.0) return false; // 在屏幕外

    // 比例 [0,1] -> 客户区像素
    double px = clipX * CLIENT_WIDTH;
    double py = clipY * CLIENT_HEIGHT;

    // 客户区像素 -> 绘制区像素（叠加层与客户区同尺寸时 ratio = 1）
    double ratioX = (double)SCREEN_WIDTH  / (double)CLIENT_WIDTH;
    double ratioY = (double)SCREEN_HEIGHT / (double)CLIENT_HEIGHT;

    *outX = px * ratioX;   // 相对绘制区左上角
    *outY = py * ratioY;
    return true;
}

// ---------------- 便捷：屏幕绝对坐标 ----------------
static bool WorldToScreenAbs(HANDLE hProcess, double wx, double wy, double wz,
                             double* absX, double* absY) {
    double sx = 0, sy = 0;
    if (!WorldToScreen(hProcess, wx, wy, wz, &sx, &sy)) return false;
    *absX = CLIENT_X + sx;
    *absY = CLIENT_Y + sy;
    return true;
}

// ---------------- 使用示例 ----------------
// int main() {
//     DWORD pid = 0;                       // 目标进程 PID
//     HANDLE hProc = OpenProcess(PROCESS_VM_READ, FALSE, pid);
//     if (!hProc) return 1;
//
//     double sx = 0, sy = 0;
//     // 换成你要标注的世界坐标
//     if (WorldToScreen(hProc, /*worldX*/ 0.0, /*worldY*/ 0.0, /*worldZ*/ 0.0, &sx, &sy))
//         printf("screen = (%.1f, %.1f)\\n", sx, sy);
//     else
//         printf("不可见（相机后方 / 屏幕外 / 读取失败）\\n");
//
//     CloseHandle(hProc);
//     return 0;
// }
`;
}
