# Win UI Auto

基于 **uiautomation** 与 **pynput** 的 Windows 桌面 UI 辅助工具：交互式探查控件、生成 XPath、命令行定位与高亮/点击。常规使用**无需管理员权限**（部分高权限窗口可能仍无法抓取）。

---

## 环境准备

推荐使用 **uv**（与本仓库 `pyproject.toml` / `uv.lock` 一致）：

```powershell
cd win_ui_auto
uv sync
```

也可自行安装依赖（版本以 `pyproject.toml` 为准）：

```powershell
pip install uiautomation pynput psutil
```

---

## 命令总览

以下参数**互斥**，每次只能选一种模式：

| 参数 | 说明 |
|------|------|
| `--find` | 交互式探查：悬停高亮、**Ctrl + 左键**抓取控件信息并写入 `el.json` |
| `--get` | 按 XPath 定位元素，输出 JSON（`--type full`）或子树文本列表（`--type text`） |
| `--if` | 按 XPath 判断元素是否存在，打印 `True` / `False` |
| `--hl` | 按 XPath 高亮目标（可选 `--match` / `--deep` / `--index`） |
| `--clk` | 按 XPath 点击目标（同上修饰参数） |
| `--v` | 打印版本号 |

通用修饰参数：

- `xpath`：位置参数，XPath 字符串（含空格时请加引号）。
- `--timeout`：定位超时（秒），默认 `10.0`。
- `--match` / `--master`：在 **XPath 最后一档匹配到的每一个实例** 下，按 Name/Value 做 **fnmatch** 模糊匹配（可写 `*`、`?`）；`--deep` 为最大递归深度。
- `--deep`：配合 `--match` 时的最大递归深度。
- `--index`：从 1 开始；无 `--match` 时表示 **同一条 XPath 最后一档枚举中的第 N 个控件**（如多个相同 `ClassName` 的按钮）；配合 `--match` 时表示过滤结果列表中的第 N 个。

---

## 1. 探查模式 `--find`

```powershell
uv run python main.py --find
# 或
py main.py --find
```

### 行为说明

- 启动后**默认已开启探查模式**（无需再输入 `1`，除非你曾用 `2` 关闭过）。
- 鼠标移到控件上，停留约 **0.8 秒**（`constants.py` 中 `HOVER_DELAY`）出现红色高亮框（外扩 **2px**，见 `HIGHLIGHT_PADDING_PX`）。
- **按住 Ctrl 再点鼠标左键**：在遮罩上完成一次“抓取”，控制台打印 JSON，并写入 **`el.json`**；XPath 会尝试写入系统剪贴板（Win32 剪贴板 API，64 位句柄安全）。
- **不按 Ctrl 时**：不挡普通左键，目标应用可正常接收点击。
- **松开 Ctrl**：探测遮罩 HWND 会 **`DestroyWindow` 销毁**（不再长期占 UIA 树）；再次按住 Ctrl 会重新创建。隐藏/显示遮罩用 **`ShowWindowAsync`**，避免在 UIA 线程里直接 `ShowWindow` 导致仍命中遮罩。
- 探查模式下若鼠标持续 **未移动** 超过 `INSPECT_MOUSE_IDLE_TIMEOUT_SECONDS`（默认 10 秒），会自动退出探查模式。

### 控制台命令

| 输入 | 作用 |
|------|------|
| `1` | 开启探查模式 |
| `2` | 关闭探查模式 |
| `clear` | 清除高亮与当前锁定控件 |
| `wq` | 退出程序 |

---

## 2. 获取元素信息 `--get`

```powershell
py main.py --get "//Window[@ClassName='Notepad' and @ProcessName='Notepad.exe']//Text[@Name='编辑' and @ClassName='TextBlock']"
```

- **`--type full`（默认）**：输出与探查口径接近的 JSON（含 `xpath`、`parent` 等，由 `control_info.get_control_info` 生成）。
- **`--type text`**：在基准节点下递归抽取文本，`--deep` 控制深度；结果为 JSON 数组。

示例（仅文本）：

```powershell
py main.py --get "//Window[@ClassName='Notepad' and @ProcessName='Notepad.exe']" --type text --deep 3
```

---

## 3. 是否存在 `--if`

```powershell
py main.py --if "//Window[@ClassName='Notepad' and @ProcessName='Notepad.exe']//Button[@Name='确定']"
```

标准输出为 **`True`** 或 **`False`**（无其它输出时便于脚本判断）。

---

## 4. 高亮 `--hl` 与 点击 `--clk`

```powershell
py main.py --hl "//Window[@ClassName='Notepad' and @ProcessName='Notepad.exe']//Text[@Name='编辑' and @ClassName='TextBlock']"
py main.py --clk "//Window[@ClassName='Notepad' and @ProcessName='Notepad.exe']//Button[@Name='确定']"
```

**同一 XPath 命中多个控件时**（例如最后一档多个按钮仅 `ClassName` 不同）：不加 `--match` 时，`--hl` 会 **依次高亮全部**；`--clk` 默认点第一个，用 **`--index N`** 点第 N 个。

带模糊匹配子元素时：

```powershell
py main.py --hl "//Window[@ClassName='Notepad' and @ProcessName='Notepad.exe']" --match "*编辑*" --deep 8 --index 1
```

---

## 5. XPath 书写要点（与定位器一致）

- 路径中 **`//` 表示任意深度后代**，解析后会转为内部“后代搜索”语义。
- 控件类型写 **`Window`、`Pane`、`Button`** 等即可（实现会自动补 `Control` 后缀与 `uiautomation` 对接）。
- 属性条件支持：
  - 分节：`Window[@ClassName='X'][@ProcessName='Y.exe']`
  - 同节多条件：`Window[@ClassName='X' and @ProcessName='Y.exe']`（**推荐**）；解析器也会识别连续多个 **`@key='...'`**（中间可省略 `and`）。
- **`@ProcessName`**：值为该窗口所属进程的 **可执行文件名**（如 `Notepad.exe`）。第一段若带进程名，定位器会枚举桌面子窗口，按进程名筛候选再寻路；支持 **通配**（如 `Note*.exe`），无通配时比较为 **大小写不敏感**。
- **`@ClassName` / `@Name` / `@AutomationId`**：属性值中若含 **`*` 或 `?`**，按 **fnmatch** 语义匹配控件上的真实属性（通配段不会交给 UIA 做整串精确匹配）；手写 XPath 仍可使用 `@AutomationId`。
- 索引：`Button[...][3]` 中末尾 **`[n]`** 表示第 n 个匹配；**通配场景**下指「满足 fnmatch 后的第 n 个」。
- **探查默认生成的 XPath**：为减少 WinUI 等框架下 **运行时变化的 `AutomationId`** 带来的脆弱性，生成器 **默认不写 `@AutomationId`**（见 `xpath_generator.py` 中 `OMIT_AUTOMATION_ID_IN_XPATH`）；需要时可将该常量改为 `True` 或手写进 XPath。

---

## 6. 打包为可执行文件

仓库根目录执行：

```powershell
uv run python build.py
```

构建逻辑见 `build.py`：读取 `uv version` 注入版本，再调用 **Nuitka** 编译 `main.py`。  
Nuitka 选项以 **`main.py` 顶部的 `# nuitka-project:` 注释**为准（当前为 **standalone 目录产物**，输出目录见注释中的 `--output-dir` / `--output-filename`）。

---

## 7. 输出文件

| 文件 | 说明 |
|------|------|
| `el.json` | 探查抓取最后一次写入的控件信息（覆盖写入） |
| `rpa_debug.log` | 仅当 `constants.DEBUG = True` 时由 `main.py` 侧写调试日志 |

---

## 8. 常见问题

- **控制台中文乱码**：`main.py` 已尝试将控制台设为 UTF-8；若仍异常，请使用支持 UTF-8 的终端（如 Windows Terminal）并选用 UTF-8 代码页。
- **杀软删除或 exe 变为 0 字节**：未签名 + 自动化/钩子类程序易被误报；已改为目录版 standalone 可降低概率；长期仍建议代码签名与企业白名单。
- **PUA 字符的 Name**（如 ``）：多为图标字体私用区字形，不是编码损坏；定位时尽量用 **`ClassName` + `Name` 通配**、**`--index`** 或手写 **`@AutomationId`** 等组合。

更多实现细节见 **`description/README.md`**。
