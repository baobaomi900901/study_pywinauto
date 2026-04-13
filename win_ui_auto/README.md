# Win UI Auto - Windows 界面自动化辅助工具

基于 `uiautomation` 和 `pynput` 的 Windows 界面控件信息获取与自动化操作工具。无需管理员权限，支持鼠标悬停高亮、一键抓取控件信息，并提供命令行接口用于文本提取和控件操作（点击/高亮），方便编写自动化脚本。

## 功能特点

- **探查模式**：鼠标悬停 0.8 秒 → 红色高亮框显示当前控件；按 `F8` 输出控件完整 JSON 信息（类型、名称、位置、Value、父级链、进程等）
- **文本获取**：通过 XPath 定位容器，提取指定深度内的文本内容
- **动作执行**：通过 XPath 定位容器，查找控件（支持通配符）并执行**点击**或**高亮**操作，支持同时高亮多个匹配项或按索引单独操作
- **无需管理员权限**，安全无干扰
- 支持命令行统一调度，也可交互式运行探查模式

## 目录结构

```
win_ui_auto/
├── hooks/
│ ├── get_text.py # 文本获取实现
│ └── set_act.py # 控件操作实现（点击/高亮，支持通配符和索引）
├── main.py # 统一入口，解析命令行参数并调度各模块
├── constants.py # 配置常量（悬停延迟、清除延迟等）
├── highlight.py # 高亮窗口（基于 Tkinter）
├── control_info.py # 控件信息获取（深层控件、信息提取、打印 JSON）
├── process_utils.py # 进程名获取
├── listeners.py # 键盘/鼠标监听（pynput 回调）
└── probe.py # UIProbe 核心类，组装各模块并管理线程
```

## 安装依赖

```
pip install uiautomation pynput
```

## 使用方式

### 1. 探查模式（交互式抓取控件信息）

```
py main.py --find-el
```

进入探查模式后，控制台会显示交互菜单：

- 1 – 开启探查模式
- 2 – 关闭探查模式
- clear – 清除当前高亮框
- wq – 退出程序

操作步骤：

- 输入 1 开启探查模式
- 鼠标移动到目标控件上，停留约 0.8 秒 → 红色高亮框显示
- 按下键盘 F8 → 控制台打印该控件的详细 JSON 信息（包含父级链、进程名等）

### 2. 命令行模式（统一调度）

支持三种互斥模式：--find-el（探查）、--get-text（获取文本）、--set-act（执行动作）。

#### 2.1 获取文本

```
py main.py --get-text <xpath> [depth] [--timeout TIMEOUT]
```

- xpath：容器控件的简化 XPath（例如 //Window[@ClassName='...']/Pane）
- depth（可选）：递归深度，默认 1
- --timeout：定位超时时间（秒），默认 10.0

**示例：**

```
py main.py --get-text "//Window[@ClassName='TScpCommanderForm']/Pane" 2
```

#### 2.2 执行动作（点击/高亮控件）

```
py main.py --set-act <xpath> <button_text> (-c [n] | -l [n]) [--timeout TIMEOUT]
```

- xpath：容器控件的 XPath
- button_text：要匹配的控件文字，支持通配符 \*（任意字符）和 ?（单个字符）
- -c [n]：点击模式。不带 n 时点击第一个匹配控件；带 n（整数，从0开始）时点击第 n 个匹配控件
- -l [n]：高亮模式。不带 n 时高亮所有匹配控件；带 n 时只高亮第 n 个匹配控件
- --timeout：定位超时时间（秒），默认 10.0

通配符匹配：大小写不敏感，例如 "掩码提示\*" 会匹配所有以“掩码提示”开头的控件。

**示例：**

```
# 高亮所有名称包含“掩码提示”的控件
py main.py --set-act "//Window[@ClassName='TScpCommanderForm'][1]/Window[@Name='选择']" "掩码提示*" -l

# 只高亮第 2 个匹配控件（索引 1）
py main.py --set-act "//Window[...]" "掩码提示*" -l 1

# 点击第 1 个匹配控件（索引 0）
py main.py --set-act "//Window[...]" "掩码提示*" -c 0

# 点击第一个匹配控件（不指定索引）
py main.py --set-act "//Window[...]" "掩码提示*" -c

```

## XPath 语法说明

采用简化 XPath，格式为：/Step1/Step2/...，每个步骤形如 ControlType[@Attr='value'][index]。

- ControlType：控件类型名（如 Window、Pane、Button、Edit 等），不要加 “Control” 后缀（框架会自动补全）
- 属性筛选：@ClassName='...'、@Name='...'、@AutomationId='...'
- 索引：[1] 表示第 1 个匹配的子控件（从 1 开始）

**示例：**

```
//Window[@ClassName='TScpCommanderForm'][1]/Window[@Name='选择']/Button[@Name='确定']

```

## 代码说明

### win_ui_auto/main.py

这段代码是一个专门用于 Windows UI 自动化测试或 RPA（机器人流程自动化）的命令行总控程序（入口文件）。

它的核心作用是接收命令行指令，将任务分发给具体的子模块（如抓取元素、获取文本、执行点击），并在所有操作开始前，利用一个“黑科技”手段强制唤醒目标应用程序的 UI 渲染。

以下是针对这段代码的简要说明和核心逻辑分析：

1. 核心亮点：“系统级护航” (强制唤醒 CEF 渲染)
   代码中最有价值的部分是 enable_os_accessibility() 和 disable_os_accessibility() 这两个函数。

痛点背景：现代桌面应用（如微信、企业微信、QQ、网易云音乐等）大量使用了基于 Chromium (CEF) 或 Electron 的 Web 架构。为了节省性能，这些应用通常开启了“惰性渲染”，即默认不向操作系统暴露其内部的 UI 节点树（DOM 树），导致传统的 UIAutomation 工具抓不到元素。

解决方案：代码通过调用 Windows 底层 API (ctypes.windll.user32.SystemParametersInfoW)，向全系统广播“屏幕阅读器（如讲述人）已开启”的欺骗信号 (SPI_SETSCREENREADER)。

效果：这会逼迫所有支持无障碍访问的应用程序（包括那些偷懒的 CEF 应用）立刻激活并生成完整的 UI 节点树，从而确保后续的 XPath 能够成功定位到元素。

2. 三大核心工作模式
   通过 argparse，该脚本定义了三个互斥的命令行核心功能：

探测模式 (--find-el)：

作用：启动 UIProbe 模块。从代码注释来看，这应该是一个类似于“审查元素”的工具，允许用户在界面上按 F8 来抓取鼠标悬停位置的 UI 元素信息（如 XPath、控件类型等）。

获取文本模式 (--get-text)：

作用：根据提供的 xpath 定位元素，并获取其内部的文本。

参数：支持传入 extra 作为 depth（深度），可能用于控制获取子节点文本的层级。

执行动作模式 (--set-act)：

作用：定位到特定元素并执行交互（点击或高亮）。

参数：必须提供 xpath 和 button_text（这里的 extra 被用作按钮文本）。

修饰参数：可以使用 -c/--click（点击）或 -l/--highlight（高亮）。支持带数字参数（如 -c 1 代表点击第二个匹配的元素，索引从 0 开始）。

3. 代码健壮性设计
   安全退出机制：在 main 函数的核心执行区使用了 try...finally... 结构。这非常关键，因为程序前面强行修改了操作系统的无障碍状态，如果自动化脚本因为找不到元素而报错崩溃，finally 块确保了 disable_os_accessibility() 一定会被执行，从而将系统状态恢复原样，避免对用户日常使用造成干扰。

严格的参数校验：脚本在执行前会检查互斥逻辑，例如明确禁止“同时点击和高亮” (-c 和 -l 同用)，并强制要求 --set-act 必须绑定一个动作。

路径隔离：文件开头主动将项目根目录加入 sys.path，确保了无论用户在哪个目录下执行终端命令，都能正确找到 hooks 和 probe 模块。

总结
这是一个设计得很成熟的 UI 自动化调度脚本。它既解决了 CEF 框架应用“元素抓取难”的根本痛点，又提供了标准化的命令行接口（CLI），非常适合作为底层服务被上层脚本（如 Python 业务逻辑或批处理文件）调用

### win_ui_auto/probe.py

这段 probe.py 中的 UIProbe 类，正是我们在分析 main.py 时推演出的 “桌面版 F12 审查元素”工具。它的底层依赖确实是 uiautomation 库。

这段代码的设计非常精彩，不仅有着严密的线程同步机制，还隐藏了针对 Chromium (CEF) 架构的第二个“黑科技”。

以下是针对 UIProbe 模块的核心逻辑与作用分析：

1. 核心亮点：“绝杀2” —— 强制穿透 CEF 渲染窗口
   如果说 main.py 中的“系统护航”是全频段的广播轰炸，那么 \_wake_up_com_interface 就是精准的狙击打击。

痛点背景：某些顽固的基于 Electron/CEF 开发的现代应用（如微信、钉钉等），其内部负责渲染网页的句柄类名通常叫 Chrome_RenderWidgetHostHWND。这些窗口有时会忽略操作系统的全局无障碍广播，依然保持静默（UI 树为空）。

黑客级解决方案：

当鼠标悬停时，利用 Win32 API (WindowFromPoint 和 GetAncestor) 找到鼠标所在的最顶层窗口。

利用 EnumChildWindows 遍历该窗口下的所有子句柄，精准搜寻 Chrome_RenderWidgetHostHWND。

一旦找到，直接调用底层 oleacc.AccessibleObjectFromWindow API，并传入 OBJID_CLIENT (-4)，向该句柄强行索要 IAccessible (COM 接口) 对象。

效果：这相当于用枪指着 Chromium 渲染引擎的脑袋，逼迫它立刻交出当前悬停位置的底层 DOM 节点数据，彻底击穿“透明防弹玻璃”，保证后续的 get_deepest_control 能抓到真实元素。

2. 优秀的性能优化：多线程与“防抖 (Debounce)”机制
   UI 自动化探测极易消耗 CPU 资源，但这个类通过优雅的架构设计解决了这个问题：

数据生产与消费分离：

MouseMoveListener 是生产者，负责以极高的频率捕获鼠标坐标，但它绝对不在回调中进行 UI 探测，而是仅仅将坐标存入 self.latest_coord（通过 coord_lock 加锁保证线程安全）。

\_uia_worker 线程是消费者，它在后台死循环中默默工作。

悬停防抖 (HOVER_DELAY)：

\_uia_worker 不会处理鼠标移动的每一个像素。它会判断鼠标是否在同一位置停留了足够的时间（(now - last_move_time) >= HOVER_DELAY）。只有当用户鼠标“停住”时，才会触发昂贵的 COM 接口唤醒和 UI 树遍历操作。这极大地保障了工具运行时的系统流畅度。

3. 工作流转与状态机
   交互层 (run 方法)：运行在主线程，提供了一个简单的命令行交互界面（CLI）。用户可以通过输入 1（开启探查）、2（暂停探查）、clear（清理屏幕红框）来控制工具状态。

视觉反馈 (highlight)：结合 \_uia_worker 的工作结果，一旦拿到当前鼠标下的 UI 节点 (control)，立刻提取其屏幕坐标 (BoundingRectangle)，并通知 HighlightWindow 在屏幕上画一个红色边框。

数据捕获 (\_on_f8)：监听全局 F8 热键。按下时，从线程安全的变量中取出当前锁定的 control，调用外部模块 get_control_info 提取各种属性（如 XPath、ClassName 等），打印到控制台，并写入本地文件供开发者编写自动化脚本使用。

总结
UIProbe 是一个高性能、低侵入性的 UI 节点嗅探器。它巧妙结合了全局 Hook（监听键鼠）、多线程并发控制、防抖算法，以及深度的 Windows UIA/MSAA 混合强制唤醒技术。这使得它不仅能抓取原生的 Windows 控件，更能无缝对付高度封装的跨平台 Web UI 框架。

### win_ui_auto/control_info.py

是整个 UI 自动化框架的**“数据大脑”或“特征提取引擎”**。

如果说 probe.py 是在前线负责按快门的侦察兵，那么 control_info.py 就是后方的情报分析室。它负责把鼠标指着的那个模糊的“点”，解析成结构化、可复用、能精准定位的身份信息档案。

以下是这段代码的核心逻辑与绝妙设计拆解：

1. 穿透与过滤：get_deepest_control
   作用：找准真正的目标。当你把鼠标放在一个按钮上时，坐标点实际上重叠了“桌面 -> 主窗口 -> 容器面板 -> 按钮”好几层控件。这个函数的作用是从最外层一直往下“钻（Drill-down）”，直到找到不能再分的叶子节点。

防误伤机制 (is_highlight_window)：这是个极其聪明的细节。探测器会在目标上画一个红框（TkChild），如果不加过滤，探测器会把自己的红框当成目标控件，导致无限死循环或抓取失败。这个函数精准地把“自己人”（红框的 PID）给剔除了。

2. 探底与嗅探：detect_automation_type
   作用：这是一个“底层技术嗅探器”。Windows 历史悠久，应用程序的底层技术五花八门。这个函数通过尝试获取控件的不同模式（Patterns），来推断它是哪种技术构建的：

UIA (UI Automation)：微软现代的无障碍接口（如 WPF、UWP 或较新的跨平台应用）。如果控件支持 Value、Invoke 等模式，判定为 UIA。

MSAA (Microsoft Active Accessibility)：老旧的接口体系。如果只能拿到 LegacyIAccessiblePattern，判定为 MSAA。

WND (Win32 原生)：最古老的原生窗口控件（如老版记事本的 Edit 或对话框 #32770）。

意义：知道对方的底牌，才能决定一会儿用什么武器去攻击（点击/输入）。不同的技术类型，交互 API 是完全不同的。

3. 族谱溯源与特征打包：get_control_info
   这是整个文件最核心、最长的方法，它完成了一次完美的信息采集：

个体特征提取：抓取目标的位置 (position)、类型 (ControlType)、类名 (ClassName)、名称 (Name)、是否是密码框等。

同级排位计算 (index & same_type_index)：这是为了生成 XPath 做准备。比如一个面板里有 3 个相同的按钮，它会算出当前控件是“所有兄弟中的第几个”，以及“同类型兄弟中的第几个”。

向上查户口 (parent_chain)：它不仅看当前控件，还会通过 GetParentControl() 一路向上溯源，直到桌面根节点。把爷爷、爸爸的类名和类型都记录下来，形成一条完整的UI 节点链条。在这个过程中，顺便把所属应用程序的 PID 和进程名 (app_info) 给查出来了。

移交组装：把整理好的族谱信息交给 generate_xpath，生成出那个最终可以被自动化脚本调用的 xpath 字符串。

4. 输出与落盘
   去重防抖 (print_control_info)：由于探测器是高频循环调用的，为了防止控制台被同样的信息疯狂刷屏，它在内部生成了一个 ctrl_id（基于类型、名字和大致坐标），只有当鼠标移到新控件，或者过了设定的时间间隔，才会打印一次 JSON。

写入文件 (write_control_info_to_file)：将这份沉甸甸的 JSON 情报写入本地的 el.json。这正是为了让外部的 Python 脚本或开发者能够直接读取这个文件，复制里面的 XPath 去写自动化代码。

总结：
这个文件处理了 UI 自动化中最脏、最累的活儿——状态树解析。它容错性极高，把复杂的 Windows UI 对象转换成了标准的、人类可读的 JSON 数据字典。

现在，前线的“探测”和“情报解析”我们都已经摸透了。接下来你想看哪部分？ 是去看看 xpath_generator.py（它是如何根据这份族谱生成 XPath 魔法字符串的），还是直捣黄龙，去看动作执行器 hooks/set_act.py（看它拿到 XPath 后如何真正操控软件）？

### win_ui_auto/xpath_generator.py

是整个框架的**“翻译官”或“咒语锻造炉”**。

在上一节 control_info.py 中，我们获取了目标控件厚厚的“族谱档案”（包含它自己以及它所有祖先的特征）。而这个模块的任务，就是把这份厚重的档案，精炼成一句能够被自动化库瞬间识别的**“魔法咒语” —— XPath 字符串**。

这短短几十行代码看似简单，却蕴含了 UI 自动化中生成可靠定位器的核心启发式策略 (Heuristics)。以下是它的精妙之处拆解：

1. 智能去根除噪 (filtered_parents)
   逻辑：代码第一步就是 [p for p in parent_chain if not p.get("is_desktop", False)]。

作用：将“桌面 (Desktop)”这个绝对根节点踢出局。

意义：如果把桌面加进去，生成的 XPath 就是绝对路径。一旦用户的电脑外接了显示器，或者在不同的 Windows 版本上运行，桌面的层级可能会发生微小变化导致脚本大面积失效。砍掉桌面，从应用程序的主窗口（//Window）开始定位，保证了极高的跨环境鲁棒性。

2. 定位降级策略 (The Fallback Strategy)
   在 \_make_segment 方法中，展示了如何为一个节点挑选最靠谱的定位属性，它的优先级策略极其符合真实的测试工程经验：

第一顺位：按 Name 定位
如果控件有名字（且不为空），它会毫不犹豫地使用 @Name='...'（例如 Button[@Name='登录']），并且抛弃索引位置。因为 UI 的名字通常是业务语义，非常稳定。即便开发人员在它前面加了三个新按钮（索引变了），只要名字叫“登录”，就能稳定找到。

第二顺位：降级为 ClassName + Index
如果控件没有名字（比如网页里大量没有标签的 <div> 或桌面应用里的布局容器），它就会退而求其次，使用类名结合位置来定位（例如 Pane[@ClassName='Chrome_WidgetWin_0'][2]）。

3. 填平编程语言与 XPath 的代沟
   索引转换：注意这一行 position = same_type_index + 1。Python 和绝大多数编程语言的数组索引是从 0 开始的，但是 XPath 规范的索引是从 1 开始的。这里如果不加 1，生成的 XPath 就会找错元素或者直接报错。这是一个非常细心且致命的细节。

4. 极致的可读性优化
   瘦身魔法 (\_short_type)：原生的 UIA 节点类型名称都带有冗长的后缀，比如 WindowControl, ButtonControl, PaneControl。这个模块通过 USE_SHORT_XPATH 标志，直接把后面的 "Control" 砍掉。

效果：将原本反人类的 //WindowControl/PaneControl/ButtonControl 瘦身为清爽的 //Window/Pane/Button，极大地减轻了编写和维护自动化脚本的开发者的视觉负担。

总结
到目前为止，我们已经彻底打通了**“探测 (Probe) -> 解析 (Control Info) -> 生成路径 (XPath)”**的整条侦察链路。这个框架不仅能强行唤醒 CEF 架构获取 DOM 树，还能极其聪明地为你生成最稳定、最短的定位代码。

### win_ui_auto/listenersm.py

这段代码 listeners.py 是整个 UI 自动化框架的**“感官神经”系统**。它的核心作用是在后台全局监听用户的物理输入（鼠标移动和键盘按键）。

它几乎是为你之前发给我的 probe.py (探测器模块) 量身定制的。

以下是具体的原理解析和关联说明：

1. 它是干嘛的？(核心作用)
   这个文件基于著名的第三方库 pynput 进行了极简的二次封装，暴露了两个类：

KeyboardListener (键盘监听器)：

作用：它在后台挂起一个线程，死死盯着用户的键盘。代码里写死了只关心一个键——F8 (keyboard.Key.f8)。一旦检测到用户按下了 F8，它就会立刻调用传入的 on_f8 回调函数。

MouseMoveListener (鼠标监听器)：

作用：它同样在后台挂起一个线程，盯着鼠标的轨迹。只要鼠标在屏幕上移动哪怕一个像素，它就会捕获当前的 X 和 Y 坐标，并丢给 on_move 回调函数去处理。

2. 它和哪个文件有直接关系？
   它直接且深度绑定着我们前面分析过的 probe.py (UIProbe 类)。

你可以回想一下 probe.py 里的这几行初始化代码：

Python
self.keyboard = KeyboardListener(on_f8=self.\_on_f8)
self.mouse_move = MouseMoveListener(on_move=self.\_on_mouse_move)
它们是这样打配合的（生产者-消费者模式）：

鼠标配合：listeners.py 里的 MouseMoveListener 就像个不知疲倦的雷达，疯狂向外发送鼠标当前的 (x, y) 坐标。而 probe.py 接收到坐标后，并不会立刻去查 UI，而是把坐标存进带锁的变量里（防抖），等鼠标真正停下来，才去调用耗时的 COM 接口去抓取 UI 元素。

键盘配合：当鼠标停在某个目标上（比如“登录”按钮），探测器画出了红框，此时用户按下 F8。listeners.py 里的 KeyboardListener 瞬间捕获到按键，触发 probe.py 的 \_on_f8 方法，进而将那个“登录”按钮的 XPath 属性全部打印并写入到 el.json 文件中。

3. 架构设计的巧思（为什么要单独拎出来写？）
   你可能会问：既然只有 probe.py 在用它，为什么不直接把这几行代码写进 probe.py 里？

这体现了作者**“关注点分离 (Separation of Concerns)”**的良好编程习惯：

解耦：probe.py 的核心业务是处理复杂的 Windows UIA 树和高亮逻辑，它不应该关心底层是如何 Hook 全局鼠标键盘事件的。

安全启停：通过封装 start() 和 stop() 方法，使得探测器在退出时（比如用户输入 wq），可以非常优雅且安全地关掉底层监听线程，防止出现后台幽灵进程或资源泄露。

### win_ui_auto/constants.py

是整个 UI 自动化框架的**“全局控制台”或“变速箱”**。

在软件工程中，把这些控制时间、频率的“魔法数字（Magic Numbers）”从核心业务逻辑中抽离出来，集中放在一个文件里，是非常标准的最佳实践。

这些参数几乎全部是服务于咱们之前分析过的 probe.py（探测器模块） 的。以下是它们各自的具体作用和背后的设计考量：

1. 核心体验控制：防抖与刷新
   HOVER_DELAY = 0.8 (悬停延迟)：

作用：这就是探测器里的防抖（Debounce）核心参数。当你在屏幕上滑动鼠标时，探测器并不会立刻去查底层 UI（因为查 UI 是非常消耗 CPU 的）。它会静静等待，只有当你的鼠标在同一个位置停留超过 0.8 秒，它才认为：“哦，原来你想要看这个控件的信息”，然后触发高亮和信息抓取。

意义：这个值决定了工具的“手感”。设得太小（比如 0.1），鼠标稍微一动电脑就狂转；设得太大（比如 2.0），用户会觉得工具卡顿、反应迟钝。0.8 秒是一个兼顾性能和体验的黄金平衡点。

CLEAR_DELAY = 0.05 (清除高亮后的延迟)：

作用：当鼠标移开旧控件，准备高亮新控件时，探测器会先调用 highlight.clear() 删掉屏幕上的红框，然后强制睡 0.05 秒。

意义：这个极短的停顿是为了防止“防弹玻璃穿透”机制误伤自己。我们在 control_info.py 里看到过防误伤逻辑，如果不加这 0.05 秒延迟，底层 COM 接口去抓 UI 时，很可能会把还没来得及从屏幕上消失的旧红框当成目标控件给抓回来。

2. 性能与功耗控制：CPU 降温器
   LOOP_SLEEP = 0.03 (探测循环睡眠时间)：

作用：当按 1 开启了探测模式后，后台线程 \_uia_worker 疯狂运转的时间间隔。0.03 秒意味着它一秒钟大约循环 33 次（约 33 FPS）。

意义：这保证了高亮红框能非常丝滑地跟上鼠标的移动，同时又不会让 CPU 占用率飙升到 100%。

NON_INSPECT_SLEEP = 0.1 (非探查模式下的睡眠)：

作用：当你按 2 关闭探测模式后，后台线程并不会死掉，而是进入了“节能模式”。

意义：此时循环间隔变长到 0.1 秒，极大降低了工具在后台挂机时的资源消耗。

3. 其他辅助
   QUEUE_TIMEOUT = 0.1：通常用于线程间通信（比如队列读取时设置的最大阻塞时间），防止死锁。

DEBUG = False：全局的调试开关。如果改成 True，开发者可能会在控制台看到更多底层的日志（比如坐标变化、COM 接口调用状态等）。
