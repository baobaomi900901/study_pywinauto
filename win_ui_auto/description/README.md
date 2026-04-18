# Win UI Auto — 技术说明

本文描述**当前代码**中的实现要点与模块关系（与根目录 `README.md` 分工：此处偏设计与实现，彼处偏使用与示例）。

---

## 1. 总入口 `main.py`

- 使用 **argparse** 定义互斥子命令：`--find` / `--get` / `--if` / `--hl` / `--clk` / `--v`。
- 启动早期调用 **`_configure_utf8_console()`**：尽量将标准输出/错误设为 UTF-8，并在 Windows 上尝试切换控制台代码页，减少中文与特殊字符打印异常。
- **`enable_os_accessibility()` / `disable_os_accessibility()`**：通过 `SystemParametersInfoW(SPI_SETSCREENREADER, …)` 临时改变系统“屏幕阅读器”相关状态，促使部分应用（尤其惰性渲染的宿主）更积极暴露 UIA 树；**`finally` 中必须恢复**，避免残留全局状态。
- **`force_wake_up_all_cef()`**：针对特定进程名（如企业微信相关）枚举子窗口，对 `Chrome_RenderWidgetHostHWND` 等句柄调用 **`AccessibleObjectFromWindow`**，作为对“全局护航”的补充唤醒手段。
- 将项目根目录加入 **`sys.path`**，保证从任意工作目录启动时能找到 `hooks`、`probe` 等包。

---

## 2. 探查管线 `probe.py`

### 2.1 线程与数据流

- **`MouseMoveListener`（`listeners.py`）**：pynput 鼠标移动回调，只写入 `latest_coord`，不在回调里做 UIA。
- **`_uia_worker`（独立线程 + `uiautomation.UIAutomationInitializerInThread`）**：
  - 消费坐标；在探查模式下满足 **`HOVER_DELAY`** 后才做昂贵路径：清高亮 → **短暂隐藏全屏遮罩**（`CaptureOverlay.hide()` → **`ShowWindowAsync`**）→ **`_wake_up_com_interface`** → **`get_deepest_control`** → 更新高亮与 `current_control`。
  - 遮罩会挡住 `ControlFromPoint`，故命中前隐藏遮罩是刻意设计；**`get_deepest_control`** 会跳过 **`WinUiAuto_CaptureOverlay`**，并在仍命中遮罩时返回 **`None`** 以回退到悬停缓存的 `current_control`。
- **探查模式空闲退出**：若 `inspect_mode` 为真且鼠标静止超过 **`INSPECT_MOUSE_IDLE_TIMEOUT_SECONDS`**，调用 **`_exit_inspect_mode`**。

### 2.2 抓取回调 `_on_ctrl_click_capture`

- 由 **`CaptureOverlay`** 在 **Ctrl + 左键** 时触发（与旧版 F8 键盘抓取无关）。
- 使用 **`get_control_info`** 生成结构化信息；可选 **CEF XPath 规整**（`_optimize_cef_xpath` + `psutil` 进程名）。
- 默认 XPath 由 **`xpath_generator.generate_xpath`** 生成：常量 **`OMIT_AUTOMATION_ID_IN_XPATH = True`** 时不在路径中写入 **`@AutomationId`**（外壳与 **`_make_segment`** 逐段均生效），避免 WinUI 等动态 Id；已移除「仅 AutomationId 跨级」优先策略，改为 **Name + ClassName** 或逐层回退。
- XPath 写入剪贴板：**Win32 `OpenClipboard` / `SetClipboardData(CF_UNICODETEXT)`**；`kernel32.GlobalAlloc/Lock/...` 与句柄使用 **`c_void_p`** 等正确原型，避免 64 位 **`OverflowError`**。
- 成功后 **`write_control_info_to_file`** 写 **`el.json`**，并自动退出探查模式以防连点。

### 2.3 调试

- **`_probe_debug_print`**：仅在 `constants.DEBUG` 为真时使用，向 stderr 输出；**勿再引用 `main.write_main_log`**，避免循环依赖或未定义符号。

---

## 3. 全屏遮罩 `capture_overlay.py`

- 独立 **Win32 线程 + 消息循环**；仅在 **探查开启且按住 Ctrl** 时 **`CreateWindowEx`** 创建顶层 **`WS_EX_LAYERED`** 遮罩，低不透明度接鼠标。
- **定时器（约 30ms）** 轮询 **`GetKeyState(VK_CONTROL)`** 与探查开关：
  - 需要遮罩：**显示**并取消 **`WS_EX_TRANSPARENT`** → **吞掉 Ctrl+左键** 并调用 **`on_capture`**（仅入队坐标，**UIA/COM 在 `_uia_worker`** 执行）。
  - **松开 Ctrl 或关闭探查**：对当前 HWND **`DestroyWindow`**，避免长期占位 UIA；再次按住 Ctrl 会进入下一轮 **创建 → 消息泵**。
- **跨线程隐藏/显示**：`hide()` / `show()` 使用 **`ShowWindowAsync`**；`show()` 内用 **`SendMessageW(WM_APP+63)`** 在遮罩线程摘掉 **`WS_EX_TRANSPARENT`**（避免 UIA 线程直接改样式无效）。
- 退出：主线程 **`PostMessage(WM_CLOSE)`**，在创建线程内 **`DestroyWindow`**（符合 Win32 线程归属）。
- **`SetWindowLongW` + `SetWindowPos(..., SWP_FRAMECHANGED)`** 用于刷新扩展样式；HWND 使用 **`c_void_p`** 承载。

---

## 4. 高亮 `highlight.py`

- 独立 **Tk 线程**：`overrideredirect` + `topmost` + `transparentcolor` 绘制红框。
- **`HIGHLIGHT_PADDING_PX`**：在 `update()` 时对矩形做外扩，减轻边缘命中抖动。
- **`get_pid()`**：供 `control_info.is_highlight_window` 过滤“自己的高亮窗口”，避免自指。

---

## 5. 控件信息与 XPath `control_info.py` / `xpath_generator.py`

- **`get_deepest_control`**：`ControlFromPoint` 后沿子树向下钻取包含坐标的最深节点；跳过本进程 **Tk 高亮** 与 **`WinUiAuto_CaptureOverlay`**（**`is_capture_overlay`**）。
- **`get_control_info`**：汇总 Name/ClassName/Value/Legacy、父链、`application`（窗口级 PID/进程名），调用 **`generate_xpath`**；父链生成前会过滤遮罩节点（见 **`xpath_generator._filter_parent_chain`**）。
- **`detect_automation_type`**：基于 Pattern 可用性做粗分类（UIA / MSAA / WND），用于信息展示；**`GetClassNameW`** 等 Win32 调用经 **`process_utils`**，避免 64 位 HWND **`ctypes` 溢出**。

---

## 6. 定位引擎 `hooks/locator.py`

- **`_parse_xpath_steps`**：将 XPath 中的 `//` 规范为 **`/descendant::`** 后拆成 **steps**；属性支持 **`and`** 或连续多个 **`@key='...'`**。
- 每步默认用 **`uiautomation.Control(...)`**（`searchFromControl`、`searchDepth`、`foundIndex`）；若 **`@Name` / `@ClassName` / `@AutomationId`** 的值含 **`*` 或 `?`**，则对该步做 **扫描 + `fnmatch`**（通配字段不传入 UIA 精确条件）。
- **`@ProcessName`（第一段）**：枚举桌面子控件，用 **`_process_name_matches`** 筛进程名（**无通配：小写精确**；**有通配：`fnmatch`**）。
- **`locate_all_by_xpath`**：先走到最后一档锚点，再 **`foundIndex` 1..N** 枚举（通配步则扫描后过滤），供 **`--hl` 全量高亮**、**`--clk --index`**、**`--match` 多基准子树搜索**。
- **`locate_by_xpath`** 常规路径与 **`_locate_from_node`** 共用 **`_resolve_one_step`**（含 **Chrome `DocumentControl` 桥接重试**）。
- **CEF 断层**：`DocumentControl` 上 `Exists` 失败时 **`bridge_to_renderer`**（**`EnumChildWindows` + `ControlFromHandle`**）。
- **遮罩 XPath**：若段中含 **`WinUiAuto_CaptureOverlay`**，直接提示并放弃（该 HWND 仅在 `--find` 按住 Ctrl 时存在）。

---

## 7. 子命令 Hooks

| 模块 | 职责 |
|------|------|
| `hooks/get.py` | `--get`：`locate_by_xpath` 后 `get_control_info` 或 `extract_recursive` |
| `hooks/el_if.py` | `--if`：定位 + `Exists` + 有效矩形 |
| `hooks/hl.py` | 无 `--match`：**`locate_all_by_xpath`** 后依次高亮；有 `--match`：对每个 XPath 匹配实例 **`find_matches_recursive`**，**`is_same_control` 去重** |
| `hooks/clk.py` | 无 `--match`：**`locate_all_by_xpath`** + **`--index`**；有 `--match`：同上多基准递归后去重，再 **`Click(simulateMove=False)`** |

`hl.py` / `clk.py` 的 **`--match`** 与 **`locator`** 分层：**先 XPath（可多实例）**，再 **Name/Value 的 fnmatch 子树过滤**。

---

## 8. 输入监听 `listeners.py`

- 当前仅保留 **`MouseMoveListener`**（全局鼠标移动）。  
- **Ctrl 状态**不由 pynput 键盘监听维护，而由遮罩层 **`GetKeyState`** 驱动，减少重复监听与杀软敏感面。

---

## 9. 常量 `constants.py`

| 常量 | 用途 |
|------|------|
| `HOVER_DELAY` | 悬停防抖后再做 UIA 命中 |
| `CLEAR_DELAY` | 高亮清除后的短延迟 |
| `LOOP_SLEEP` / `NON_INSPECT_SLEEP` | 探查开/关下的循环节拍 |
| `INSPECT_MOUSE_IDLE_TIMEOUT_SECONDS` | 探查模式鼠标静止自动退出 |
| `HIGHLIGHT_PADDING_PX` | 高亮矩形外扩像素 |
| `DEBUG` | 调试输出总开关；`probe._uia_worker` 异常时可选 **`traceback.print_exc()`** |

---

## 10. 构建 `build.py`

- **`uv version --output-format json`** 读取包名与版本，生成临时 **`_version.py`** 供 Nuitka/运行时读取。
- 调用 **`uv run python -m nuitka ... main.py`**；**具体编译开关以 `main.py` 内 `# nuitka-project:` 为准**。

---

## 11. COM / MSAA 在本项目中的位置

- **`AccessibleObjectFromWindow` + `IID_IAccessible`**：在探查的 **`_wake_up_com_interface`** 与 **`main.force_wake_up_all_cef`** 中用于“点醒”渲染 HWND，促使底层暴露可访问对象。
- **日常定位**：以 **UIAutomation** 为主；部分控件通过 **LegacyIAccessiblePattern** 与 MSAA 桥接共存。

---

## 12. 已知取舍

- **全局无障碍 SPI**：有效但有副作用，务必保证进程退出时恢复。
- **pynput**：需要系统允许低级钩子；企业环境可能受限。
- **Tk 高亮线程**：与主线程分离；避免在后台线程再创建/销毁 Tk 根窗口（剪贴板已改为 Win32）。
