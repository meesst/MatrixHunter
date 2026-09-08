# MatrixHunter 开发规格说明书

> 版本：1.0（深化版）
> 日期：2026-07-23
> 状态：可编码实施

---

## 0. 文档说明

本文档为 MatrixHunter 的唯一开发依据，覆盖需求、架构、接口、数据结构、算法、业务流程、边界条件、异常处理、性能约束与测试策略。开发团队应**严格依据本文档编码**，任何与文档冲突的实现都视为缺陷。

本文档已基于原始方案完成以下深化与修正：
1. **修正 3×4 矩阵列主序定义混乱**：明确 3×4 仅采用行主序补第 4 行，不枚举补第 4 列方案；
2. **补全坐标系对齐**：明确投影坐标基准为目标窗口客户区，叠加层精确覆盖客户区并跟随窗口变化；
3. **修正 64 位读 32 位进程的不准确表述**：说明 `ReadProcessMemory` 的跨位数行为；
4. **新增 DPI 感知**：避免高 DPI 屏幕坐标错乱；
5. **新增线程安全模型**：明确读取线程与 GUI 线程的职责边界与同步机制；
6. **砍掉精确点模式**：仅保留象限过滤模式；
7. **区分命名**：世界坐标记作 `W`，齐次裁剪分量记作 `clip-w`，消除原方案撞名；
8. **形式化所有数据结构与接口签名**，穷举边界条件与异常码。

---

## 1. 项目总览

### 1.1 软件名称
MatrixHunter

### 1.2 目标
通用的内存矩阵发现与验证工具。用户输入一批疑似矩阵地址与一个静态世界坐标 `W`，软件自动枚举所有矩阵解释方案，通过"世界坐标 → 屏幕象限"反复过滤，最终筛选出正确的**地址 + 矩阵方案**，并支持实时叠加绘制验证。

### 1.3 核心特性
- **零矩阵知识假设**：用户无需理解行/列主序、乘法方向等概念，软件自动枚举所有解释组合。
- **通杀性**：不绑定特定游戏，支持 32/64 位进程、float/double 数据类型。
- **象限过滤**：用户只需视觉判断目标位于哪个象限（四选一），软件淘汰不符方案。
- **实时绘制验证**：选定方案后，在目标窗口客户区叠加绘制圆圈，随视角移动验证正确性。

### 1.4 适用与不适用
- **适用**：目标进程未受反作弊保护（或用户已具备读取权限）；矩阵为单个组合矩阵（ViewProj 或等价物）；矩阵数据在内存中连续存储。
- **不适用**：View/Proj 分离存储（需双地址相乘，本期不支持）；矩阵数据非连续存储；强反作弊环境（`OpenProcess` 被拦截）。

---

## 2. 术语与约定

| 术语 | 含义 |
|---|---|
| `W` | 世界坐标，用户提供的静态目标三维坐标 `(x, y, z)`，被变换的输入点 |
| `clip-w` | 齐次裁剪坐标的第 4 分量，即变换后向量 `t` 的 `t[3]`，用于透视除法。**不是**世界坐标 W |
| 矩阵方案 (Scheme) | 对一个地址的一种完整解释：形状 + 布局 + 乘法方向 + clip-w 符号 |
| 候选池 | 当前未被淘汰的所有矩阵方案的集合 |
| 客户区 | 目标进程主窗口的客户区（不含标题栏/边框），投影坐标的基准 |
| 叠加层 | 覆盖目标窗口客户区的透明置顶窗口，用于绘制十字线与验证圆圈 |
| NDC | 归一化设备坐标，`[-1, 1]` 范围 |

### 数值约定
- 所有地址以十六进制输入，支持带 `0x` 前缀或不带（如 `23F28408D80` 与 `0x23F28408D80` 等价）。
- 浮点比较使用相对/绝对容差，定义见 §10.2。
- 角度、坐标系一律采用屏幕空间：原点在客户区左上角，X 向右增，Y 向下增。

---

## 3. 技术选型与依赖

| 维度 | 选型 | 版本约束 | 理由 |
|---|---|---|---|
| 语言 | Python | 3.11+ | 库丰富，原型迭代快 |
| GUI | PySide6 | 6.6+ | 成熟，支持透明无边框窗口、高 DPI |
| 内存读写 | pymem | 1.13+ | 封装 `ReadProcessMemory`，自动处理 32/64 位句柄 |
| 进程信息 | psutil | 5.9+ | 进程列表、PID、位数判断 |
| Win32 API | pywin32 | 306+ | 窗口查找、客户区坐标、鼠标穿透、DPI |
| 数学 | numpy | 1.26+ | 矩阵向量运算 |
| 打包 | PyInstaller | 6.0+ | 单 exe 分发 |

### 关于跨位数内存读取的准确说明
`pymem` 底层调用 `kernel32.OpenProcess` + `kernel32.ReadProcessMemory`。在 64 位 Windows 上，64 位 Python 进程通过 `ReadProcessMemory` **可直接读取 32 位（WoW64）与 64 位目标进程的虚拟内存**，无需特殊 WoW64 适配 API——`ReadProcessMemory` 本身按目标进程的虚拟地址空间解析。位数检测仅用于**显示与诊断**，不改变读取路径。

### requirements.txt
```
PySide6>=6.6
pymem>=1.13
psutil>=5.9
pywin32>=306
numpy>=1.26
pyinstaller>=6.0
```

---

## 4. 系统架构

### 4.1 目录结构
```
MatrixHunter/
├── main.py                       # 入口
├── ui/
│   ├── main_window.py            # 主窗口
│   ├── overlay.py                # 叠加层窗口
│   └── widgets.py                # 复用控件（地址表、方案表）
├── core/
│   ├── memory_reader.py          # 内存读取封装
│   ├── process_manager.py        # 进程检测/附加/窗口定位
│   ├── matrix_enumerator.py      # 矩阵方案枚举
│   ├── projector.py              # 世界→屏幕投影
│   ├── filter_engine.py          # 过滤引擎（候选池管理）
│   └── scheme.py                 # 数据结构定义（Scheme 等）
├── infra/
│   ├── config.py                 # 配置持久化
│   ├── logger.py                 # 日志
│   └── threading_helpers.py      # 线程安全工具（读写锁、信号槽桥接）
├── tests/
│   ├── test_matrix_enumerator.py
│   ├── test_projector.py
│   └── test_filter_engine.py
└── MatrixHunter_开发规格说明书.md
```

### 4.2 线程模型

| 线程 | 职责 | 频率 |
|---|---|---|
| **GUI 主线程** | 界面交互、过滤触发、方案表更新、叠加层 `paintEvent` | 事件驱动 |
| **窗口跟踪线程** | 轮询目标窗口客户区位置/大小，移动叠加层 | 10 Hz（100ms） |
| **实时绘制读取线程** | 启用实时绘制时，读取选中方案矩阵数据并投影，发信号给 GUI 重绘 | 30 Hz（~33ms） |

**同步规则**：
- 候选池（`FilterEngine.schemes`）的**读**（过滤、显示）由 GUI 线程独占；**写**（淘汰、重置）也由 GUI 线程独占。过滤操作同步在 GUI 线程完成，不涉及子线程。
- 实时绘制线程**只读取**"当前选中方案"引用及其地址，**不修改候选池**。选中方案的切换由 GUI 线程通过原子赋值完成（Python GIL 下引用赋值原子）。
- 窗口跟踪线程**只调用** Win32 API 与 `overlay.move/resize`（Qt 控件几何操作须在 GUI 线程），故通过 `QMetaObject.invokeMethod` 或信号投递到 GUI 线程执行。

### 4.3 模块依赖（单向）
```
ui  ──► core ──► infra
        │
        └─► scheme (数据结构，被所有 core 模块依赖)
```

---

## 5. 核心数据结构定义

所有数据结构定义在 `core/scheme.py`，使用 `dataclass`。

### 5.1 枚举类型

```python
from enum import Enum

class MatrixShape(Enum):
    """矩阵形状"""
    FULL_4x4 = "4x4"        # 16 个数，完整 4x4
    ROW3x4 = "3x4"           # 12 个数，行主序，补第 4 行 [0,0,0,1]

class MemoryLayout(Enum):
    """内存布局"""
    ROW_MAJOR = "row_major"  # 行主序: M[i][j] = d[i*4 + j]
    COL_MAJOR = "col_major"  # 列主序: M[i][j] = d[j*4 + i]

class MulDirection(Enum):
    """向量乘法方向"""
    VEC_MUL_M = "v*M"        # 行向量: t = v @ M
    M_MUL_VEC = "M*v"        # 列向量: t = M @ v

class ClipWSign(Enum):
    """clip-w 符号"""
    POSITIVE = "+w"          # clip_w = t[3]
    NEGATIVE = "-w"          # clip_w = -t[3]

class DataType(Enum):
    """数据类型"""
    FLOAT = "float"          # 32 位单精度，4 字节
    DOUBLE = "double"        # 64 位双精度，8 字节

class Quadrant(Enum):
    """屏幕象限（以客户区中心为原点）"""
    TOP_LEFT = "TL"
    TOP_RIGHT = "TR"
    BOTTOM_LEFT = "BL"
    BOTTOM_RIGHT = "BR"

class SchemeStatus(Enum):
    """方案状态"""
    ACTIVE = "active"        # 在候选池中
    ELIMINATED = "eliminated"  # 已淘汰
```

### 5.2 矩阵方案 `MatrixScheme`

```python
from dataclasses import dataclass, field
import numpy as np

@dataclass(frozen=True)
class MatrixScheme:
    """一个地址的一种完整矩阵解释方案。不可变。"""
    scheme_id: str                 # 唯一 ID，如 "addr_0x23F..._4x4_row_v*M_+w"
    address: int                   # 矩阵头地址（十进制整数）
    data_type: DataType
    shape: MatrixShape
    layout: MemoryLayout           # 对 ROW3x4 固定为 ROW_MAJOR
    mul_direction: MulDirection
    clip_w_sign: ClipWSign

    @property
    def element_count(self) -> int:
        """需读取的浮点数个数"""
        return 16 if self.shape is MatrixShape.FULL_4x4 else 12

    @property
    def byte_size(self) -> int:
        """需读取的字节数"""
        elem_bytes = 4 if self.data_type is DataType.FLOAT else 8
        return self.element_count * elem_bytes

    @property
    def description(self) -> str:
        """人类可读描述，用于结果表展示"""
        return (f"{self.shape.value} {self.layout.value} "
                f"{self.mul_direction.value} {self.clip_w_sign.value} "
                f"{self.data_type.value}")

    def build_matrix(self, raw: list[float]) -> np.ndarray:
        """将原始浮点数列表构建为 4x4 numpy 矩阵。
        raw 长度必须 == element_count。
        """
        ...  # 实现见 §7.1
```

> **说明**：`ROW3x4` 形状的 `layout` 固定为 `ROW_MAJOR`，枚举时不生成 `ROW3x4 + COL_MAJOR` 组合（见 §7.1 枚举规则）。

### 5.3 测试点 `FilterPoint`

```python
@dataclass(frozen=True)
class WorldCoord:
    x: float
    y: float
    z: float

@dataclass(frozen=True)
class FilterPoint:
    """一次过滤的输入：世界坐标 + 用户判断的象限"""
    world: WorldCoord
    quadrant: Quadrant
    # 注：象限模式不需要屏幕像素坐标，仅需象限归属
```

### 5.4 投影结果 `ProjectionResult`

```python
from dataclasses import dataclass

@dataclass
class ProjectionResult:
    """一次投影的输出"""
    visible: bool              # 是否可见（clip_w > epsilon 且落点在客户区内）
    screen_x: float            # 客户区像素 X（visible=False 时无意义）
    screen_y: float            # 客户区像素 Y
    quadrant: Quadrant         # 落点所属象限（visible=False 时无意义）
    clip_w: float              # clip-w 原值（诊断用）
    reason: str                # 不可见原因："ok"|"clip_w_le_zero"|"nan_or_inf"|"out_of_client"
```

### 5.5 过滤结果 `FilterOutcome`

```python
@dataclass
class FilterOutcome:
    """一次过滤的统计"""
    before_count: int          # 过滤前候选数
    after_count: int           # 过滤后候选数
    eliminated_ids: list[str]  # 被淘汰的 scheme_id 列表
```

### 5.6 配置 `AppConfig`

```python
@dataclass
class AppConfig:
    # 过滤
    clip_w_epsilon: float = 1e-6          # clip-w 可见性阈值
    # 实时绘制
    realtime_fps: int = 30                # 实时绘制读取频率
    circle_radius_px: int = 8             # 验证圆圈半径（像素）
    circle_color: tuple[int, int, int] = (0, 255, 0)  # 绿色
    # 窗口跟踪
    window_track_interval_ms: int = 100   # 窗口跟踪轮询间隔
    # 诊断
    log_level: str = "INFO"
```

---

## 6. 模块接口规范

### 6.1 `core/process_manager.py` — 进程与窗口管理

```python
class ProcessManager:
    """进程检测、附加、目标窗口定位。"""

    def list_processes(self) -> list[tuple[int, str, bool]]:
        """枚举进程。
        Returns: [(pid, process_name, is_64bit), ...]
        is_64bit: True=64位进程, False=32位(WoW64)进程。
        实现: psutil.process_iter + psutil.Process(pid).is_wow64()
              (64位系统上 is_wow64()=True 即 32 位进程)
        Raises: ProcessListError
        """

    def attach(self, pid: int) -> None:
        """附加到目标进程。
        Raises:
            AttachError - 进程不存在或 OpenProcess 失败
        实现: pymem.Pymem() + open_process_from_id
        """

    def find_main_window(self, pid: int) -> int | None:
        """查找目标进程的主窗口句柄 hwnd。
        实现: EnumWindows + GetWindowThreadProcessId 匹配 pid，
              取具有 WS_VISIBLE 且无父窗口的最大客户区窗口。
        Returns: hwnd 或 None(未找到)
        """

    def get_client_rect_on_screen(self, hwnd: int) -> tuple[int, int, int, int] | None:
        """获取客户区在屏幕坐标系中的位置与大小。
        Returns: (screen_x, screen_y, width, height) 或 None(窗口无效)
        实现: GetClientRect + ClientToScreen(左上角)
        注意: 需处理 DPI，调用前确保进程 DPI 感知(见 §11.2)。
        """

    def detach(self) -> None:
        """断开附加。"""
```

**异常定义**（infra/logger.py 或各模块内）：
```python
class MatrixHunterError(Exception): ...           # 基类
class ProcessListError(MatrixHunterError): ...
class AttachError(MatrixHunterError): ...
class MemoryReadError(MatrixHunterError): ...
class InvalidAddressError(MatrixHunterError): ...
class EnumerationError(MatrixHunterError): ...
```

### 6.2 `core/memory_reader.py` — 内存读取

```python
class MemoryReader:
    """批量读取浮点数。生命周期与 ProcessManager.attach 绑定。"""

    def __init__(self, pm: 'pymem.Pymem', data_type: DataType):
        """pm 为已附加的 Pymem 实例；data_type 决定单元素字节数。"""

    def read_floats(self, address: int, count: int) -> list[float]:
        """从 address 读取 count 个浮点数。
        Raises:
            InvalidAddressError - address 非法或为 0
            MemoryReadError - ReadProcessMemory 失败（跨页/未分配/权限不足/进程退出）
        返回长度恒等于 count，否则视为错误抛异常。
        实现: pm.read_bytes(address, count*elem_bytes) + struct.unpack
        float 用 '<f', double 用 '<d' (小端，x86/x64 标准)。
        """

    def read_floats_batch(self, addresses: list[tuple[int, int]]) -> dict[int, list[float] | Exception]:
        """批量读取多个 (address, count)。
        Returns: {address: list[float] 或 Exception}
        单个地址失败不影响其他地址（异常作为值返回，不抛出）。
        用途: 过滤前批量刷新所有候选方案的数据。
        """
```

**边界**：
- `address == 0` → `InvalidAddressError`
- `count <= 0` → 返回空列表
- 读取字节数跨过分页边界且部分未分配 → `ReadProcessMemory` 返回失败 → `MemoryReadError`，**不返回部分数据**
- 目标进程退出 → `MemoryReadError`（错误码 `PROCESS_EXITED`）

### 6.3 `core/matrix_enumerator.py` — 方案枚举

```python
class MatrixEnumerator:
    """根据地址 + 数据类型生成所有候选矩阵方案。"""

    @staticmethod
    def enumerate(address: int, data_type: DataType) -> list[MatrixScheme]:
        """对单个地址生成全部候选方案。
        枚举维度（见 §7.1）:
          shape ∈ {FULL_4x4, ROW3x4}
          layout: FULL_4x4 → {ROW_MAJOR, COL_MAJOR}; ROW3x4 → {ROW_MAJOR} 固定
          mul_direction ∈ {VEC_MUL_M, M_MUL_VEC}
          clip_w_sign ∈ {POSITIVE, NEGATIVE}
        总数 = 2(布局,仅4x4贡献2) + 1(3x4固定行主序) ... 
        实际 = (2*2*2) [4x4] + (1*2*2) [3x4] = 8 + 4 = 12 种
        Raises:
            InvalidAddressError - address 非法
        """

    @staticmethod
    def enumerate_batch(addresses: list[int], data_type: DataType) -> list[MatrixScheme]:
        """对一批地址批量枚举。"""
```

### 6.4 `core/projector.py` — 投影

```python
class Projector:
    """世界坐标 → 客户区屏幕坐标 → 象限。"""

    def __init__(self, client_width: int, client_height: int, config: AppConfig):
        ...

    def set_client_size(self, width: int, height: int) -> None:
        """客户区尺寸变更时调用（窗口跟踪触发）。"""

    def project(self, scheme: MatrixScheme, matrix: np.ndarray,
                world: WorldCoord) -> ProjectionResult:
        """执行投影。
        matrix: 已由 scheme.build_matrix 构建的 4x4 矩阵。
        算法见 §7.2。
        """

    def quadrant_of(self, screen_x: float, screen_y: float) -> Quadrant:
        """判定像素坐标所属象限（以客户区中心为界）。
        边界规则: screen_x == center_x 归右(TR/BR); screen_y == center_y 归下(BL/BR)。
        """
```

### 6.5 `core/filter_engine.py` — 过滤引擎

```python
class FilterEngine:
    """候选池管理 + 象限过滤。所有方法在 GUI 线程调用。"""

    def __init__(self, config: AppConfig):
        ...

    def load_schemes(self, schemes: list[MatrixScheme]) -> None:
        """重置候选池为给定方案列表（清空已有）。"""

    def reset(self) -> None:
        """清空候选池。"""

    @property
    def active_schemes(self) -> list[MatrixScheme]:
        """当前存活方案（只读视图）。"""

    @property
    def active_count(self) -> int:
        ...

    def filter(self, points: list[tuple[MatrixScheme, np.ndarray, FilterPoint]],
               projector: Projector) -> FilterOutcome:
        """执行一轮过滤。
        points: [(scheme, matrix, filter_point), ...] 仅含当前 active 方案及其矩阵数据。
        规则: 对每个方案，用每个 FilterPoint 投影并比对象限；
              任一 FilterPoint 不匹配 → 淘汰该方案（一票否决）。
        Returns: FilterOutcome
        """
```

> **过滤原子性**：一轮过滤内，所有方案的判定基于同一批矩阵数据快照与同一组 FilterPoint，中途不插入新数据。

### 6.6 `ui/main_window.py` — 主窗口（接口要点）

主窗口聚合上述模块，提供以下信号/槽（Qt 信号）：
- `sig_filter_triggered(WorldCoord, Quadrant)` — 用户点击"添加并过滤"
- `sig_realtime_toggled(bool)` — 实时绘制开关
- `sig_scheme_selected(str)` — 用户在结果表选中某 scheme_id
- `sig_process_attached(int pid, bool is64bit)` — 进程附加完成

### 6.7 `ui/overlay.py` — 叠加层（接口要点）

```python
class OverlayWindow(QWidget):
    """透明置顶无边框窗口，覆盖目标客户区。"""
    def align_to_client(self, screen_x, screen_y, w, h): ...   # 由窗口跟踪调用
    def set_crosshair_visible(bool): ...
    def set_realtime_point(self, x: float | None, y: float | None): ...
    # paintEvent: 绘制十字线 + 实时圆圈
```

---

## 7. 核心算法详细设计

### 7.1 矩阵方案枚举

**输入**：地址 `A`，数据类型 `DT`。

**枚举规则**：

| 组 | shape | layout | mul_direction | clip_w_sign | 数量 |
|---|---|---|---|---|---|
| 1 | FULL_4x4 | ROW_MAJOR | VEC_MUL_M | POSITIVE | 1 |
| 2 | FULL_4x4 | ROW_MAJOR | VEC_MUL_M | NEGATIVE | 1 |
| 3 | FULL_4x4 | ROW_MAJOR | M_MUL_VEC | POSITIVE | 1 |
| 4 | FULL_4x4 | ROW_MAJOR | M_MUL_VEC | NEGATIVE | 1 |
| 5 | FULL_4x4 | COL_MAJOR | VEC_MUL_M | POSITIVE | 1 |
| 6 | FULL_4x4 | COL_MAJOR | VEC_MUL_M | NEGATIVE | 1 |
| 7 | FULL_4x4 | COL_MAJOR | M_MUL_VEC | POSITIVE | 1 |
| 8 | FULL_4x4 | COL_MAJOR | M_MUL_VEC | NEGATIVE | 1 |
| 9 | ROW3x4 | ROW_MAJOR(固定) | VEC_MUL_M | POSITIVE | 1 |
| 10 | ROW3x4 | ROW_MAJOR(固定) | VEC_MUL_M | NEGATIVE | 1 |
| 11 | ROW3x4 | ROW_MAJOR(固定) | M_MUL_VEC | POSITIVE | 1 |
| 12 | ROW3x4 | ROW_MAJOR(固定) | M_MUL_VEC | NEGATIVE | 1 |

**合计 12 种/地址**。

> **冗余说明**：数学上 `FULL_4x4 + ROW_MAJOR + VEC_MUL_M` 与 `FULL_4x4 + COL_MAJOR + M_MUL_VEC` 对同一组数据互为等价（转置关系）。枚举两者无害，仅多一次计算；保留以简化实现逻辑、降低出错风险。文档不剔除。

**`build_matrix(raw)` 实现**：

```python
def build_matrix(self, raw: list[float]) -> np.ndarray:
    assert len(raw) == self.element_count
    if self.shape is MatrixShape.FULL_4x4:
        d = raw
        if self.layout is MemoryLayout.ROW_MAJOR:
            M = np.array(d, dtype=np.float64).reshape(4, 4)        # M[i][j]=d[i*4+j]
        else:  # COL_MAJOR
            M = np.array(d, dtype=np.float64).reshape(4, 4, order='F')  # M[i][j]=d[j*4+i]
    else:  # ROW3x4, layout 固定 ROW_MAJOR
        rows = [raw[i*4:(i+1)*4] for i in range(3)]
        rows.append([0.0, 0.0, 0.0, 1.0])                          # 补第 4 行
        M = np.array(rows, dtype=np.float64)                        # 4x4
    return M
```

**读取长度策略**：为同时覆盖 4×4（16 数）与 3×4（12 数），对每个地址统一读取 `16` 个元素（float=64 字节，double=128 字节）。4×4 方案用全部 16 个；3×4 方案用前 12 个。若地址附近可读字节不足 16 个元素，则该地址所有方案标记为读取失败并从候选池移除（见 §10.3）。

### 7.2 世界 → 屏幕投影算法

**输入**：方案 `scheme`，4×4 矩阵 `M`，世界坐标 `world=(x,y,z)`，客户区 `(W_c, H_c)`。

**步骤**：

```
1. 构造齐次向量 v = [x, y, z, 1.0]  (np.array, dtype=float64)

2. 变换:
   if mul_direction == VEC_MUL_M:  t = v @ M      # (1x4) @ (4x4) = (1x4)
   else:                           t = M @ v      # (4x4) @ (4x1) = (4x1)
   t = np.asarray(t).reshape(4)                   # 统一为一维

3. 提取: tc, yc, zc, wc_raw = t[0], t[1], t[2], t[3]

4. NaN/Inf 检查:
   if not np.isfinite([tc, yc, zc, wc_raw]).all():
       return ProjectionResult(visible=False, reason="nan_or_inf")

5. clip-w 符号:
   clip_w = wc_raw if clip_w_sign == POSITIVE else -wc_raw

6. 可见性:
   if clip_w <= clip_w_epsilon:   # 包含 <=0 与极小正数
       return ProjectionResult(visible=False, reason="clip_w_le_zero", clip_w=clip_w)

7. 透视除法 (NDC):
   ndc_x = tc / clip_w
   ndc_y = yc / clip_w

8. NDC → 客户区像素:
   screen_x = (ndc_x * 0.5 + 0.5) * W_c
   screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * H_c    # Y 轴翻转: NDC 上→屏幕下

9. 客户区内判定:
   if not (0 <= screen_x <= W_c and 0 <= screen_y <= H_c):
       return ProjectionResult(visible=False, reason="out_of_client",
                               screen_x=screen_x, screen_y=screen_y, clip_w=clip_w)

10. 象限:
    quadrant = quadrant_of(screen_x, screen_y)

11. return ProjectionResult(visible=True, screen_x, screen_y, quadrant, clip_w, "ok")
```

**象限判定边界**（`quadrant_of`）：
```
cx = W_c / 2,  cy = H_c / 2
right = (screen_x >= cx)
bottom = (screen_y >= cy)
TL: not right and not bottom
TR: right and not bottom
BL: not right and bottom
BR: right and bottom
```

### 7.3 过滤算法

**一轮过滤**（用户提交一个 `FilterPoint`）：

```
对候选池中每个 active 方案 S:
    读取 S 的矩阵数据 → raw (16 元素)
    若读取失败: 标记 S 为 ELIMINATED, reason="read_failed", continue
    M = S.build_matrix(raw[:S.element_count])
    R = projector.project(S, M, filter_point.world)
    if not R.visible:
        淘汰 S  (不可见即不满足"目标在该象限"的前提)
        continue
    if R.quadrant != filter_point.quadrant:
        淘汰 S
    else:
        保留 S
返回 FilterOutcome(before, after, eliminated_ids)
```

**多 FilterPoint 批过滤**（可选，一次提交多个历史判断点）：
- 对每个方案，必须满足**全部** FilterPoint 才保留（逻辑 AND）。
- 注意：不同 FilterPoint 对应不同时刻的矩阵数据。若用户一次性提交多个历史象限判断，矩阵数据已变（视角已转），这些判断**不可叠加**——每次过滤必须基于"当前帧矩阵 + 当前视角下的单一象限判断"。**因此工具只支持"单点逐轮过滤"**，不缓存历史 FilterPoint 叠加。每轮过滤独立，基于当前读取的矩阵数据。

> **重要约束**：每轮过滤前必须**重新读取**所有 active 方案的矩阵数据（视角已变，矩阵已更新）。不可复用上一轮数据。

### 7.4 实时绘制算法

```
循环 (realtime_fps):
    S = 当前选中方案 (GUI 线程原子赋值)
    if S is None: continue
    raw = memory_reader.read_floats(S.address, 16)   # 失败则跳过本轮，记录日志
    M = S.build_matrix(raw[:S.element_count])
    R = projector.project(S, M, 当前_W)
    if R.visible:
        overlay.set_realtime_point(R.screen_x, R.screen_y)
    else:
        overlay.set_realtime_point(None, None)
    # 触发 overlay.update() 重绘 (经信号投递到 GUI 线程)
```

---

## 8. 业务流程

### 8.1 主流程（状态机）

```
[启动]
  ↓
[选择进程] ──attach──► [配置: 数据类型 + 输入地址列表 + 输入 W]
  ↓
[枚举候选] (每地址 12 方案) ──► [候选池就绪]
  ↓
┌───────────── 过滤循环 ─────────────┐
│ [用户转视角, 判断目标象限]          │
│        ↓                            │
│ [用户在 UI 选象限 + 点"过滤"]       │
│        ↓                            │
│ [重读所有 active 方案矩阵数据]      │
│        ↓                            │
│ [逐方案投影 + 象限比对 + 淘汰]      │
│        ↓                            │
│ [更新方案表/状态栏]                 │
│        ↓                            │
│ [active_count == 0?] ──是──► [无结果: 提示并允许回退/重置]
│        ↓ 否                         │
│ [用户满意?] ──否──► (回到循环顶)    │
└────────┬──是────────────────────────┘
         ↓
[用户在结果表选定一个方案]
  ↓
[开启实时绘制] ──► [实时绘制线程: 读矩阵→投影→画圆圈]
  ↓
[用户视觉验证圆圈是否跟随目标]
  ↓
[结束]
```

### 8.2 关键时序：一轮过滤

```
GUI线程                MemoryReader         FilterEngine         Projector
   │                       │                    │                   │
   │─ 用户点"过滤" ────────│                    │                   │
   │─ 读取 active 列表 ────────────────────────►│                   │
   │                       │                    │                   │
   │─ read_floats_batch ──►│                    │                   │
   │◄─ {addr: raw/err} ────│                    │                   │
   │                       │                    │                   │
   │  对每个 active 方案:   │                    │                   │
   │─ build_matrix + project ──────────────────────────────────────►│
   │◄─ ProjectionResult ────────────────────────────────────────────│
   │─ 比对象限, 决定淘汰/保留 ───────────────►│                   │
   │                       │                    │                   │
   │◄─ FilterOutcome ──────────────────────────│                   │
   │─ 刷新方案表/状态栏     │                    │                   │
```

### 8.3 叠加层对齐流程（窗口跟踪线程 → GUI 线程）

```
每 100ms:
  hwnd = process_manager.find_main_window(pid)
  if hwnd is None: 隐藏叠加层, 记日志; continue
  rect = process_manager.get_client_rect_on_screen(hwnd)
  if rect 变化: 通过信号投递 overlay.align_to_client(*rect) 到 GUI 线程
```

---

## 9. GUI 交互规范

### 9.1 主窗口布局

```
┌─────────────────────────────────────────────────────────────┐
│ 顶部: [进程下拉▼] [刷新] [数据类型: ◉float ○double]           │
│       [视口: 自动获取/手动 宽__ 高__]    状态: PID/位数/读取   │
├──────────────────────┬──────────────────────────────────────┤
│ 左: 地址列表          │ 右: 过滤区                            │
│ ┌──────────────────┐ │  世界坐标 W:  X____ Y____ Z____      │
│ │ 0x23F28408D80  ● │ │  目标象限:  [TL] [TR] [BL] [BR]      │
│ │ 0x23F28408E88  ● │ │  [添加并过滤]  [重置候选池]           │
│ │ ...             │ │  ─────────────────────────           │
│ └──────────────────┘ │  存活方案: 12 / 总 324                │
│ [加载文件] [粘贴] [清空]│                                       │
├──────────────────────┴──────────────────────────────────────┤
│ 底部: 结果表                                                 │
│ ┌────────────────────────────────────────────────────────┐  │
│ │ 地址        | 方案描述                 | 状态 | 操作      │  │
│ │ 0x23F...    | 4x4 row_major v*M +w    | 存活 | [选用][预览]│  │
│ └────────────────────────────────────────────────────────┘  │
│ [☑实时绘制(基于选中方案)]                                    │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 交互规则
- **地址输入**：文本框，一行一个十六进制地址（可带/不带 `0x`）；支持"粘贴"与"加载文件"。非法行高亮标红并忽略，合法行入表。
- **数据类型**：单选，切换后**清空候选池**并要求重新枚举。
- **过滤**：用户填 W、选象限、点"添加并过滤"。每轮过滤后结果表实时刷新。
- **回退**：提供"撤销最近一轮过滤"（保留淘汰栈，最多回退 1 轮，避免无限回溯歧义）。
- **选用方案**：双击结果表行或点"选用"，设为当前选中方案，用于实时绘制。
- **实时绘制开关**：勾选后启动实时绘制线程；取消则停止。
- **象限选择按钮**：四个按钮 `TL/TR/BL/BR`，点击即触发过滤（等价于"选象限+过滤"）。

### 9.3 叠加层
- 全程显示十字线（白色半透明，将客户区四等分），辅助用户判断象限。
- 实时绘制开启时，叠加一个绿色圆圈（半径可配，默认 8px）。
- 叠加层**鼠标穿透**（`WS_EX_TRANSPARENT | WS_EX_LAYERED`），不影响游戏操作。
- 快捷键：
  - `F8` 显示/隐藏叠加层
  - `F9` 切换实时绘制
  - `ESC` 取消实时绘制

### 9.4 状态栏信息
- 目标进程 PID、位数、进程名
- 目标窗口客户区尺寸
- 当前候选数 / 总枚举数
- 最近一次过滤结果摘要

---

## 10. 边界条件与异常处理

### 10.1 边界条件清单

| 场景 | 处理 |
|---|---|
| 地址输入为空行 | 忽略 |
| 地址非法（非十六进制） | 标红忽略，不计入 |
| 地址重复 | 去重，仅保留一份 |
| 同一地址产生 12 方案，候选池含重复地址不同方案 | 正常，各自独立判定 |
| 读取字节数不足 16 元素 | 该地址所有方案标记 `read_failed`，本轮不参与过滤；下一轮重试 |
| 矩阵含 NaN/Inf | 该方案本轮判定 `nan_or_inf`，**视为不匹配象限 → 淘汰**（不可见处理） |
| `clip_w <= epsilon` | 不可见 → 淘汰 |
| 投影落点在客户区外 | 不可见 → 淘汰 |
| 落点恰在中心线 | 按 §7.2 边界规则归右/下象限 |
| 一轮过滤后 active=0 | 弹提示"无方案满足，可撤销最近一轮或重置"；自动回退该轮（不持久化淘汰） |
| 候选数始终不收敛（>1，多轮后） | 提示用户"存在多个等价方案，选用其一即可" |
| 目标进程退出 | `MemoryReadError` → 停止实时绘制，主窗口提示"进程已退出"，要求重新附加 |
| 目标窗口最小化/隐藏 | 叠加层隐藏，暂停实时绘制；窗口恢复后自动恢复 |
| 目标窗口移动/缩放 | 窗口跟踪线程检测后重对齐叠加层；投影器 `set_client_size` 同步更新 |
| 客户区宽或高为 0 | 暂停过滤与绘制，提示"窗口客户区无效" |
| 用户未选进程即过滤 | 禁用过滤按钮 |
| 用户未填 W 即过滤 | 禁用过滤按钮，提示填 W |
| W 含 NaN | 输入校验拦截，提示"请输入有效数值" |
| 实时绘制时切换选中方案 | 原子赋值，下一帧用新方案，无锁 |
| 撤销栈为空时点撤销 | 禁用撤销按钮 |

### 10.2 浮点容差
- `clip_w_epsilon = 1e-6`：`clip_w <= epsilon` 视为不可见。
- 象限比对为**严格相等**（枚举值），无浮点容差问题。
- 矩阵数据读取后**不清洗** NaN/Inf，直接送入投影，由 §7.2 步骤 4 拦截。

### 10.3 异常处理策略

| 异常类型 | 触发点 | 处理策略 |
|---|---|---|
| `AttachError` | 附加进程 | 主窗口弹错，停留在进程选择态 |
| `InvalidAddressError` | 读取/枚举 | 跳过该地址，日志记录 |
| `MemoryReadError` | 读取单个地址 | 批量读取中作为值返回，不中断；单方案读取失败则该方案本轮淘汰 |
| `MemoryReadError`(进程退出) | 任意读取 | 停止所有读取线程，提示重新附加 |
| `EnumerationError` | 枚举 | 弹错，候选池保持空 |
| Qt 信号槽异常 | 子线程 | 捕获并经信号传递错误消息到 GUI 线程显示，不崩溃 |
| 未知异常 | 任意 | 全局 `sys.excepthook` 捕获，写日志，弹错但不退出（实时绘制线程异常则停止该线程） |

### 10.4 实时绘制线程异常隔离
- 实时绘制线程的每次循环用 `try/except` 包裹；单次读取/投影异常仅记录日志并跳过该帧，**不终止线程**。
- 连续失败超过 N 次（默认 30 次，约 1 秒）则暂停实时绘制并通知 GUI。

---

## 11. 性能约束与优化

### 11.1 量化约束

| 指标 | 约束 | 说明 |
|---|---|---|
| 单轮过滤延迟 | ≤ 500ms（100 地址以内） | 含批量读取 + 全方案投影比对 |
| 批量读取 | 单次 `read_floats_batch` 并发读取所有 active 地址 | pymem 顺序读，单地址 ~0.1ms，100 地址 ~10ms |
| 实时绘制帧率 | 30 Hz（可配） | 受读取延迟约束，最低保证 15 Hz |
| 叠加层重绘 | ≤ 16ms | 仅画十字线 + 1 圆圈，无压力 |
| 窗口跟踪延迟 | ≤ 100ms 感知窗口变化 | 10 Hz 轮询 |
| 内存占用 | ≤ 200MB | 含 PySide6/numpy 运行时 |
| 候选池规模上限 | 10000 方案 | 超出则警告并要求减少地址数 |

### 11.2 优化要点
- **批量读取**：过滤前一次性读取所有 active 方案所需数据（每地址 16 元素），避免逐方案重复读同一地址（同地址的 12 方案共享一次读取）。
- **数据复用**：同地址的 12 方案共享同一 `raw`，仅 `build_matrix` 分别构建。
- **numpy 向量化**：`build_matrix` 用 `np.array.reshape`，避免 Python 循环。
- **投影零分配**：热路径避免频繁创建数组，可预分配缓冲。
- **GUI 不阻塞**：过滤虽在 GUI 线程，但单轮 < 500ms 可接受；若地址极多导致 > 500ms，显示"过滤中"进度并考虑分批。

### 11.3 DPI 感知（强制）
- 启动时调用 `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`，确保 `GetClientRect` 返回物理像素而非逻辑像素。
- PySide6 6.x 默认启用高 DPI 缩放，叠加层几何使用物理像素坐标，与 Win32 `GetClientRect` 一致。
- 验证：在 150% 缩放屏幕上，叠加层必须精确覆盖客户区，无偏移。

---

## 12. 安全性与兼容性

### 12.1 安全性
- **权限**：仅申请 `PROCESS_VM_READ`，不申请写入权限，降低风险。
- **句柄释放**：`detach` 必须关闭 `OpenProcess` 句柄；使用上下文管理器或 `atexit` 保证释放。
- **输入校验**：所有用户输入（地址、W、分辨率）经校验后才进入核心逻辑，防止注入异常值导致崩溃。
- **日志**：不记录矩阵数值（可能含敏感数据），仅记录地址、方案 ID、过滤统计、异常栈。
- **无持久化敏感数据**：配置文件仅存窗口位置、最近进程名、容差等，不存地址或坐标。

### 12.2 兼容性
- **OS**：Windows 10 1903+ / Windows 11（需 PER_MONITOR_AWARE_V2 支持）。
- **Python**：3.11+，仅 64 位 Python（64 位 Python 可读 32/64 位目标进程）。
- **目标进程**：32 位与 64 位用户态进程；不支持内核态/受 PPL 保护进程。
- **多显示器**：叠加层跟随目标窗口所在显示器，坐标用屏幕绝对坐标。
- **打包**：PyInstaller 单 exe，64 位；在 64 位 Windows 上运行，可读 32/64 位进程。

---

## 13. 测试策略

### 13.1 单元测试（pytest）

| 模块 | 测试要点 |
|---|---|
| `matrix_enumerator` | 单地址生成恰好 12 方案；`ROW3x4` 的 layout 恒为 ROW_MAJOR；scheme_id 唯一 |
| `build_matrix` | 行主序/列主序互为转置；3×4 补第 4 行 `[0,0,0,1]`；输入长度不符抛异常 |
| `projector` | 已知正确矩阵投影误差 < 1px；clip_w≤0 判不可见；NaN/Inf 判不可见；象限边界归右/下；Y 轴翻转正确 |
| `filter_engine` | 单点过滤淘汰率符合预期；active=0 时回退；读取失败方案被淘汰；多方案共存 |
| `memory_reader` | mock pymem 验证字节计算；地址 0 抛 `InvalidAddressError`；读取失败抛 `MemoryReadError` |

### 13.2 集成测试
- 构造一个"假游戏"进程（测试辅助程序），写入已知 ViewProj 矩阵到固定地址，用 MatrixHunter 枚举 → 过滤 → 选出正确方案 → 实时绘制验证。
- 验证 12 方案中正确方案必在过滤后存活且可被选中。

### 13.3 边界与异常测试
- 进程退出中途过滤；窗口最小化；DPI 150% 对齐；地址跨页读取失败；1000 地址性能。

---

## 14. 打包与部署

### 14.1 PyInstaller 命令
```bash
pyinstaller --onefile --windowed --name MatrixHunter --icon=app.ico ^
  --hidden-import pymem ^
  --collect-submodules PySide6 ^
  main.py
```

### 14.2 注意事项
- `pymem` 依赖 `pymem.ressources`（含 .dll），需 `--collect-all pymem` 或确认打包包含。
- PySide6 插件（平台插件）自动收集；若启动报插件缺失，加 `--collect-all PySide6`。
- 产物体积约 80–120MB（PySide6 + numpy 主导），可接受。
- 运行环境：64 位 Windows 10 1903+，无需安装 Python。

### 14.3 交付物
- `MatrixHunter.exe`（单文件）
- `使用说明.txt`：选择进程 → 选数据类型 → 粘贴地址 → 填 W → 转视角判断象限 → 过滤 → 反复 → 选用方案 → 开实时绘制验证。

---

## 15. 开发计划

| 阶段 | 内容 | 工时 |
|---|---|---|
| 1 | 环境搭建 + pymem 读写冒烟测试 | 0.5d |
| 2 | `scheme.py` 数据结构 + `matrix_enumerator` + 单测 | 1d |
| 3 | `projector` + 单测（含边界） | 1d |
| 4 | `memory_reader` + `process_manager`（含 DPI/窗口跟踪） | 1d |
| 5 | `filter_engine` + 单测 | 0.5d |
| 6 | 主窗口 GUI + 地址表/方案表/过滤交互 | 1.5d |
| 7 | 叠加层（透明窗口/十字线/穿透/对齐） | 1.5d |
| 8 | 实时绘制线程 + 信号桥接 | 1d |
| 9 | 集成测试（假游戏进程） + 调优 | 1d |
| 10 | PyInstaller 打包 + 干净系统验证 | 0.5d |
| **合计** | | **约 9.5 工作日** |

---

## 16. 附录

### 16.1 候选方案枚举总表（12 种/地址）

| # | shape | layout | mul_direction | clip_w_sign | 元素数 |
|---|---|---|---|---|---|
| 1 | 4x4 | row_major | v*M | +w | 16 |
| 2 | 4x4 | row_major | v*M | -w | 16 |
| 3 | 4x4 | row_major | M*v | +w | 16 |
| 4 | 4x4 | row_major | M*v | -w | 16 |
| 5 | 4x4 | col_major | v*M | +w | 16 |
| 6 | 4x4 | col_major | v*M | -w | 16 |
| 7 | 4x4 | col_major | M*v | +w | 16 |
| 8 | 4x4 | col_major | M*v | -w | 16 |
| 9 | 3x4 | row_major | v*M | +w | 12 |
| 10 | 3x4 | row_major | v*M | -w | 12 |
| 11 | 3x4 | row_major | M*v | +w | 12 |
| 12 | 3x4 | row_major | M*v | -w | 12 |

### 16.2 错误码表

| 错误类 | 典型 message | 用户可见提示 |
|---|---|---|
| `AttachError` | "OpenProcess failed (code=5)" | "无法附加进程，可能权限不足或被保护" |
| `InvalidAddressError` | "address is 0 or invalid" | "地址非法" |
| `MemoryReadError` | "ReadProcessMemory failed (code=299)" | "读取失败，地址可能无效或进程已退出" |
| `MemoryReadError` | "process exited" | "目标进程已退出，请重新选择" |
| `EnumerationError` | "address invalid for enumeration" | "枚举失败" |

### 16.3 关键 Win32 API 清单

| API | 用途 |
|---|---|
| `OpenProcess` | 打开目标进程（pymem 封装） |
| `ReadProcessMemory` | 读内存（pymem 封装） |
| `EnumWindows` + `GetWindowThreadProcessId` | 查找目标进程主窗口 |
| `GetClientRect` + `ClientToScreen` | 客户区屏幕坐标 |
| `SetWindowLong(GWL_EXSTYLE, WS_EX_TRANSPARENT\|WS_EX_LAYERED)` | 叠加层鼠标穿透 |
| `SetWindowPos(HWND_TOPMOST)` | 置顶 |
| `SetProcessDpiAwarenessContext` | DPI 感知 |

### 16.4 投影公式速查

```
v = [x, y, z, 1]
t = v @ M          (v*M, 行向量)
t = M @ v          (M*v, 列向量)
clip_w = t[3] 或 -t[3]           (符号)
ndc_x = t[0] / clip_w
ndc_y = t[1] / clip_w
screen_x = (ndc_x * 0.5 + 0.5) * W_c
screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * H_c
象限: center=(W_c/2, H_c/2), 右=screen_x>=cx, 下=screen_y>=cy
```

### 16.5 需求基线确认记录

| 项 | 定论 |
|---|---|
| 数据类型 | 用户 UI 选 float/double，不自动枚举 |
| 地址位数 | 支持 64 位(8字节) 与 32 位(4字节) 地址输入 |
| 世界坐标 W | 用户自填静态目标坐标 |
| W 精度 | 用户转视角让目标稳落象限内部自控，不加中心区 |
| 叠加层 | 覆盖目标窗口客户区，跟随移动/缩放 |
| 过滤模式 | 仅象限模式（四选一），无精确点模式 |
| 形状枚举 | 4×4(行/列主序) + 3×4(仅行主序补第4行)，不枚举补第4列 |
| 矩阵假设 | 单地址=单矩阵头，不涉及 View/Proj 分离 |
| 实时绘制 | 单圆圈，基于用户选定的一种方案 |
| 候选数/地址 | 12 种 |

---

*文档结束。本规格说明书为 MatrixHunter 的唯一开发依据，任何变更须经需求方确认并更新版本号。*
