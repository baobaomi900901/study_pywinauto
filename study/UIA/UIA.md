# UIA 特征

How found: Selected from tree...

- 何种方式得到:
  - Selected from tree...：在树视图中手动选中。
  - Focus...：通过键盘焦点（Tab 键或鼠标点击）获取当前聚焦的元素。
  - ScreenPoint...：通过指定屏幕坐标点查找元素。
  - Condition...：通过特定的查找条件（如 AutomationId、Name 等）搜索得到。

背景：MSAA vs UIA

| 技术                                      | 时代               | 说明                                                          |
| ----------------------------------------- | ------------------ | ------------------------------------------------------------- |
| **MSAA (Microsoft Active Accessibility)** | 1997年引入         | 旧版无障碍标准，基于 `IAccessible` 接口和 `WM_GETOBJECT` 消息 |
| **UIA (UI Automation)**                   | Windows Vista 引入 | 现代无障碍标准，更强大灵活                                    |

为什么需要这个模式？

```
旧版屏幕阅读器/辅助工具（基于 MSAA）
         ↓
    无法直接理解 UIA 控件
         ↓
    通过 LegacyIAccessible Pattern 桥接
         ↓
    以 MSAA 方式获取控件信息（Role、State、Value、Name 等）
```

| 属性/方法                        | 对应 MSAA 概念                       |
| -------------------------------- | ------------------------------------ |
| `ChildId`                        | MSAA 子项 ID                         |
| `DefaultAction`                  | 默认操作描述                         |
| `Description`                    | 控件描述                             |
| `Help`                           | 帮助文本                             |
| `KeyboardShortcut`               | 快捷键                               |
| `Name`                           | 控件名称（与 UIA Name 对应）         |
| `Role`                           | MSAA 角色（如 ROLE_SYSTEM_BUTTON）   |
| `State`                          | MSAA 状态（如 STATE_SYSTEM_CHECKED） |
| `Value`                          | 控件值                               |
| `Select()` / `DoDefaultAction()` | MSAA 操作                            |

与标准 UIA 属性的关系

| MSAA (Legacy) | UIA 等价属性                               |
| ------------- | ------------------------------------------ |
| `Name`        | `AutomationElement.NameProperty`           |
| `Role`        | `ControlType` + `LocalizedControlType`     |
| `State`       | 各种 `IsEnabled`、`IsOffscreen` 等状态属性 |
| `Value`       | `ValuePattern.Value`                       |

---

Name: ""

- 控件的可读名称:
  - 开发者未为该控件设置 Name 或 AutomationProperties.Name。
  - 它是一个纯容器（Group），本身不需要读出名称，依赖内部子元素提供信息。
  - 但 LegacyIAccessible.Name 也是空，说明通过旧版 MSAA 接口也获取不到名称。

---

ControlType: UIA_GroupControlTypeId (0xC36A)

- ControlType 表示 UI 元素的控件类型，是 UI 自动化中区分不同 UI 元素种类（如按钮、编辑框、列表项、窗格等）的核心标识。
- UIA_GroupControlTypeId 是内部枚举值，对应的本地化名称是“组”。
- Group（组） 通常是一个逻辑容器，用来将相关的一组控件组织在一起。它本身没有固定的交互行为（不像按钮有点击、编辑框有文本），但可以承载额外的控件模式（例如本例中支持 InvokePattern，说明该组可被点击）。
- 0xC36A 就是这个“组”控件类型的身份证号

---

LocalizedControlType: "组"

- 这个属性是一个本地化字符串，会被屏幕阅读器（如讲述人、NVDA）朗读出来，告知用户当前控件的类型是“组”。
- 它通常基于 ControlType（如 UIA_GroupControlTypeId）自动生成，并匹配系统语言。由于你的系统是中文，所以显示为“组”。

---

BoundingRectangle: {l:613 t:604 r:914 b:742}

- UI 元素在屏幕坐标系中的位置和大小

---

IsEnabled: true

- UI 元素当前是否启用（可交互）
  - true：控件处于启用状态，用户可以与之交互（点击、输入等）。
  - false：控件被禁用，通常显示为灰色，无法接收键盘或鼠标输入。
  - 当父容器的 IsEnabled 为 false 时，其内部子元素通常也无法被用户点击或交互，即使子元素自身的 IsEnabled 可能仍然报告为 true。

---

IsOffscreen: false

- UI 元素当前是否位于屏幕的可视区域之外
  - true：元素完全不可见（被滚动出视口、位于虚拟屏幕外、或被其他窗口完全遮挡，但通常指由于滚动或布局导致的不可见，而非单纯被遮挡）。
  - false：元素至少有一部分在屏幕内可见。

---

IsKeyboardFocusable: false

- 表示 UI 元素是否能够通过键盘（如 Tab 键）获得焦点。
  - true：元素可以获得焦点，用户可以通过键盘（如 Tab 键）切换到该元素。
  - false：元素不能获得焦点，用户无法通过键盘切换到该元素。

HasKeyboardFocus: false

- 表示 UI 元素当前是否持有键盘焦点

> IsKeyboardFocusable 与 HasKeyboardFocus 的区别
> IsKeyboardFocusable 是能力：表示元素是否允许被键盘聚焦。
> HasKeyboardFocus 是状态：表示元素当前是否拥有键盘焦点。

---

AccessKey: ""

- UI 元素的访问键

---

ProcessId: 7436

- ProcessId 是进程标识符
  - ProcessId 是临时的“身份证号”，每次重生都会换号，不能用它来记住你是谁，但在你活着的时候可以精准地找到你。

  - 在编写自动化脚本时，如果需要在程序重启后依然能正确找到目标窗口，应该使用：
    - 进程名（ProcessName）：如 iDealWorkbench.exe，通常是固定的。
    - 可执行文件路径：更精确，但受安装位置影响。

    - 窗口标题（Name） 或 自动化 ID（AutomationId）：如果应用程序提供了稳定的属性。

    - 类名（ClassName）：部分框架下窗口类名是固定的。

---

ProviderDescription: "[pid:7436,hwnd:0x0 Main(parent link):Microsoft: MSAA Proxy (unmanaged:UIAutomationCore.DLL)]"

- UI 自动化框架用来描述UI 自动化提供程序（Provider）信息的字符串，说明该元素是由哪个提供程序、以何种方式暴露给 UI 自动化客户端的。
  - pid : 进程 ID
  - hwnd : 窗口句柄
  - Main(parent link) : 父窗口
    - M该提供程序的主要类型是 MSAA 代理（Microsoft Active Accessibility Proxy）。这表明该元素是通过 MSAA 桥接暴露给 UI 自动化的，而不是原生 UIA 提供程序。
    - (unmanaged:UIAutomationCore.DLL) : 提供程序实现位于非托管模块 UIAutomationCore.dll 中，这是 UI 自动化核心库。

---

IsPassword: false

- 是否为密码框

---

HelpText: ""

- UI 自动化中用于提供帮助信息或工具提示文本的属性，通常向用户说明控件的用途或操作指导。

---

FillColor: [Not supported]

- UI 自动化中用于描述控件填充颜色的属性，通常用于形状、图形或背景色可自定义的控件（如按钮、面板等）。
  - [Not supported] 表示不支持此属性

---

OutlineColor: [Not supported]

- UI 自动化中用于描述控件轮廓颜色的属性，通常适用于有边框、轮廓或描边的控件（如按钮、形状、可聚焦元素的高亮边框等）。

---

OutlineThickness: [Not supported]

- UI 自动化中用于描述控件轮廓粗细的属性，通常与 OutlineColor 一起表示控件边框的宽度（以像素为单位）。

---

FillType: [Not supported]

- UI 自动化中用于描述控件填充类型的属性，表示内部区域是如何被填充的（如纯色、渐变、图案、图像等）。它通常与 FillColor 配合，用于向辅助技术（屏幕阅读器）或自动化工具传递控件的视觉样式信息。

CenterPoint: [Not supported]

- UI 自动化中用于表示控件中心点坐标的属性，通常以屏幕坐标 (x, y) 的形式给出。

---

Rotation: [Not supported]

- UI 自动化中用于表示控件旋转角度的属性，通常以度（°）为单位，适用于支持变换的控件（如可旋转的图像、图形或自定义控件）。

---

Size: [Not supported]

- UI 自动化中用于表示控件尺寸的属性，通常包含宽度和高度信息。

---

VisualEffects: [Not supported]

- 是 UI 自动化中用于描述控件视觉特效的属性，如模糊、阴影、动画、透明度变化等。

---

HeadingLevel: [Not supported]

- UI 自动化中用于标识控件标题级别的属性，主要用于文档、文章或内容区域中的标题元素（类似于 HTML 中的 <h1> 到 <h9>）

---

LegacyIAccessible 是 UI 自动化为了向后兼容 MSAA 而保留的“适配层”。它的存在确保了大量基于 MSAA 的旧控件能够无缝地在 UI 自动化生态中工作，无需开发者重写代码。如果你看到一个控件的大部分现代模式（如 IsValuePatternAvailable）都是 false，但 IsLegacyIAccessiblePatternAvailable 是 true，说明该控件很可能是通过 MSAA 代理暴露的。

---

LegacyIAccessible.ChildId: 0

- LegacyIAccessible.ChildId 是 UI 自动化中为了兼容旧版 MSAA 而提供的属性，用于标识 MSAA 对象内部的子元素索引。
  - 值为 0 表示该 MSAA 对象自身，而不是其某个子元素。这是最常见的取值，代表当前控件作为一个独立的可访问对象存在。

  - 如果值 > 0，则代表该控件是某个父 MSAA 对象内的第 N 个子元素（通常用于列表项、选项卡等逻辑子对象）。

---

LegacyIAccessible.DefaultAction: "点击祖先实体"

这个字符串从何而来？

- 该控件是一个 Group，本身没有内置的默认操作，但开发者在实现自定义控件或通过 MSAA 代理时，可以显式设置 accDefaultAction 属性。

- “点击祖先实体”表明：该控件实际上是某个更大实体（祖先）的一部分，点击这个控件等同于点击它的父级或祖先级元素。常见于列表项、卡片、组合框选项等场景，整个条目区域可点击，而不仅仅是内部的文字或图标。

与 UI 自动化的关系

- 在 UIA 中，该控件的 IsInvokePatternAvailable: true，说明支持 Invoke 模式。

- MSAA 的 DefaultAction 通常会被 UIA 的 MSAA 代理自动映射为 InvokePattern.Invoke() 方法。也就是说，当客户端调用 Invoke() 时，系统内部会触发该默认操作。

---

LegacyIAccessible.Description: ""

UI 自动化中为了兼容 MSAA 而保留的属性，用于提供对控件的附加描述信息，通常比 Name 更详细，用于辅助技术向用户补充说明控件的用途或状态。

---

LegacyIAccessible.Help: ""

- 帮助文本

---

LegacyIAccessible.KeyboardShortcut: ""

- 键盘快捷键

---

LegacyIAccessible.Name: ""
LegacyIAccessible.Role: 分组 (0x14)

- 控件的角色（如“按钮”、“分组”）

---

LegacyIAccessible.State: 正常 (0x0)

- 控件的状态（如“正常”、“不可用”）

---

LegacyIAccessible.Value: ""

- 控件的值（如编辑框中的文字）

---

Selection2 是 UI 自动化中 SelectionPattern2 控件模式的简称，是 SelectionPattern 的扩展版本，用于提供更丰富的选择信息。

什么时候会支持？
支持 SelectionPattern2 的控件通常是那些实现了 ISelectionProvider2 接口的自定义控件或较新框架（如 WinUI、UWP）中的选择控件。例如：

- 列表框（ListBox）

- 选项卡控件（TabControl）

- 数据网格（DataGrid）

当控件支持时，你可以直接获取第一项、最后一项等，而不必遍历所有选中项集合。

Selection2.FirstSelectedItem: [Not supported]

- 第一个选项

Selection2.LastSelectedItem: [Not supported]

- 最后一个选项

Selection2.CurrentSelectedItem: [Not supported]

- 当前选中

Selection2.ItemCount: [Not supported]

- 选项总数

---

IsAnnotationPatternAvailable: false

- 用于指示该控件是否支持批注模式 (Annotation Pattern)。

- 作用:
  当 IsAnnotationPatternAvailable 返回 true 时，表示该 UI 元素：
  支持批注功能 — 可以添加、修改或删除批注/注释
  实现了 IAnnotationProvider 接口 — 开发者可以通过 UIA 与批注功能交互
  常用于 — 文档编辑器、PDF 阅读器、电子表格等需要注释功能的应用

- 典型应用场景:
  Microsoft Word — 批注/评论功能
  PDF 阅读器 — 高亮、注释、便签
  Excel — 单元格批注
  协作工具 — 文档审阅和反馈

---

IsDragPatternAvailable: false

- 表示该控件是否支持拖拽模式 (Drag Pattern)。

- 作用:
  当 IsDragPatternAvailable 返回 true 时，表示该 UI 元素：
  支持拖拽操作 — 可以被拖动或作为拖放目标
  实现了 IDragProvider 接口 — 开发者可以通过 UIA 控制拖拽行为
  常用于 — 文件管理器、看板应用、图形编辑器等需要拖放功能的场景

- 典型应用场景:
  Windows 资源管理器 — 拖动文件/文件夹
  任务管理工具（如 Trello、Jira）— 拖动卡片变更状态
  设计软件 — 拖动图层、组件
  音乐播放器 — 拖动歌曲调整播放列表顺序

---

IsDockPatternAvailable: false

- 表示该控件是否支持停靠模式

- 作用:
  当 IsDockPatternAvailable 返回 true 时，表示该 UI 元素：
  支持停靠布局 — 可以停靠在容器的特定边缘（上、下、左、右、填充）
  实现了 IDockProvider 接口 — 开发者可以通过 UIA 控制停靠位置
  常用于 — IDE 面板、工具窗口、可停靠的侧边栏等

- 典型应用场景:
  Visual Studio — 解决方案资源管理器、属性窗口等可停靠面板
  Photoshop/设计软件 — 工具面板、图层面板
  浏览器开发者工具 — 可停靠/分离的调试面板
  Office 应用 — 可停靠的任务窗格

---

IsDropTargetPatternAvailable: false

- 表示该控件是否支持拖放目标模式 (Drop Target Pattern)。

- 作用
  当 IsDropTargetPatternAvailable 返回 true 时，表示该 UI 元素：
  可以作为放置目标 — 其他元素可以拖放到此控件上
  实现了 IDropTargetProvider 接口 — 开发者可以通过 UIA 与放置功能交互
  常与拖拽模式配合使用 — 一个元素拖拽 (IsDragPatternAvailable)，另一个元素接收放置

---

IsExpandCollapsePatternAvailable: false

- 表示该控件是否支持展开/折叠模式 (Expand-Collapse Pattern)。

- 作用
  当 IsExpandCollapsePatternAvailable 返回 true 时，表示该 UI 元素：
  支持展开/折叠状态切换 — 可以显示或隐藏子内容
  实现了 IExpandCollapseProvider 接口 — 开发者可以通过 UIA 控制展开/折叠
  常用于 — 树形控件、分组框、下拉菜单、手风琴面板等

- 典型应用场景
  文件资源管理器 — 文件夹树形结构的展开/折叠
  导航菜单 — 侧边栏多级菜单的展开/折叠
  设置面板 — 分组设置的展开/折叠
  下拉框 (ComboBox) — 下拉列表的展开/折叠
  手风琴组件 (Accordion) — 面板的展开/折叠

---

IsGridItemPatternAvailable: false

- 表示该控件是否支持网格项模式 (Grid Item Pattern)。

- 作用:
  当 IsGridItemPatternAvailable 返回 true 时，表示该 UI 元素：
  1. 是网格/表格中的一个单元格项 — 位于网格的特定行和列
  2. 实现了 IGridItemProvider 接口 — 开发者可以通过 UIA 获取该项在网格中的位置信息
  3. 常与 IsGridPatternAvailable 配合使用 — 容器支持网格模式，子项支持网格项模式

- 典型应用场景
  Excel/电子表格 — 每个单元格都是网格项
  数据表格 (DataGrid) — 表格中的行单元格
  日历控件 — 日期格子
  图片缩略图网格 — 每个缩略图项
  属性检查器 — 属性名-值对的网格布局

---

IsGridPatternAvailable: false

- 表示该控件是否支持网格模式 (Grid Pattern)。

- 作用:
  当 IsGridPatternAvailable 返回 true 时，表示该 UI 元素：
  是一个网格/表格容器 — 包含按行和列组织的子元素
  实现了 IGridProvider 接口 — 开发者可以通过 UIA 遍历和操作网格中的项
  常与 IsGridItemPatternAvailable 配合使用 — 容器支持网格模式，子项支持网格项模式

- 典型应用场景:
  Excel/电子表格 — 整个工作表网格
  数据表格 (DataGrid) — 数据库表格展示
  日历控件 — 月份日期网格
  文件资源管理器（详细信息视图） — 文件列表网格
  属性检查器 — 属性名-值对的网格布局

---

IsInvokePatternAvailable: true

- 表示该控件是否支持调用模式 (Invoke Pattern)。

- 作用
  当 IsInvokePatternAvailable 返回 true 时，表示该 UI 元素：
  支持点击/调用操作 — 可以触发某个动作或命令
  实现了 IInvokeProvider 接口 — 开发者可以通过 UIA 以编程方式触发该控件
  是最常用的 UIA 模式之一 — 几乎所有可交互控件都支持

- 典型应用场景
  | 控件类型 | 调用效果 |
  | ------------------- | --------- |
  | **按钮 (Button)** | 点击按钮，执行命令 |
  | **菜单项 (MenuItem)** | 选择菜单项 |
  | **列表项 (ListItem)** | 选中列表项 |
  | **超链接 (Hyperlink)** | 打开链接 |
  | **工具栏按钮** | 执行工具命令 |
  | **通知/气泡提示** | 点击通知进行操作 |

- 与 IInvokeProvider 的关系

```
  控件实现了 IInvokeProvider 接口
  ↓
  UIA 暴露 IsInvokePatternAvailable = true
  ↓
  自动化工具可以调用 Invoke() 方法触发控件
```

---

IsItemContainerPatternAvailable: false

- 表示该控件是否支持项容器模式 (Item Container Pattern)。

- 作用:
  当 IsItemContainerPatternAvailable 返回 true 时，表示该 UI 元素：
  是一个虚拟化容器的项容器 — 管理大量子项，支持按需加载（虚拟化）
  实现了 IItemContainerProvider 接口 — 开发者可以通过 UIA 根据属性查找子项
  主要用于高性能大数据列表 — 避免一次性加载所有元素到内存

- 典型应用场景
  长列表虚拟化 — 如 10万条数据的列表，只渲染可见项
  ComboBox 下拉列表 — 大量选项时的性能优化
  TreeView 树形控件 — 延迟加载子节点
  DataGrid 大数据表格 — 虚拟滚动时按需获取单元格

- 与 IsVirtualizedItemPatternAvailable 的关系
  | 属性 | 角色 |
  | ----------------------------------- | ------------------------ |
  | `IsItemContainerPatternAvailable` | **容器端** — 父控件支持查找子项 |
  | `IsVirtualizedItemPatternAvailable` | **子项端** — 子项支持从虚拟状态加载到内存 |

---

IsLegacyIAccessiblePatternAvailable: true

- 示该控件是否支持旧版 IAccessible 兼容模式 (Legacy IAccessible Pattern)。

- 作用
  当 IsLegacyIAccessiblePatternAvailable 返回 true 时，表示该 UI 元素：
  支持 MSAA 旧版接口 — 兼容 Microsoft Active Accessibility (MSAA) 标准
  实现了 ILegacyIAccessibleProvider 接口 — 提供 UIA 到 MSAA 的桥接
  用于向后兼容 — 让旧版辅助技术工具能访问现代 UIA 控件

  IsMultipleViewPatternAvailable: false
  IsObjectModelPatternAvailable: false
  IsRangeValuePatternAvailable: false
  IsScrollItemPatternAvailable: false
  IsScrollPatternAvailable: false
  IsSelectionItemPatternAvailable: false
  IsSelectionPatternAvailable: false
  IsSpreadsheetItemPatternAvailable: false
  IsSpreadsheetPatternAvailable: false
  IsStylesPatternAvailable: false
  IsSynchronizedInputPatternAvailable: false
  IsTableItemPatternAvailable: false
  IsTablePatternAvailable: false
  IsTextChildPatternAvailable: false
  IsTextEditPatternAvailable: false
  IsTextPatternAvailable: false
  IsTextPattern2Available: false
  IsTogglePatternAvailable: false
  IsTransformPatternAvailable: false
  IsTransform2PatternAvailable: false
  IsValuePatternAvailable: false
  IsVirtualizedItemPatternAvailable: false
  IsWindowPatternAvailable: false
  IsCustomNavigationPatternAvailable: false
  IsSelectionPattern2Available: [Not supported]
  FirstChild: "" 图像
  LastChild: "" 组
  Next: [null]
  Previous: [null]
  Other Props: Object has no additional properties
  Children: "" 图像
  "" 组
  "" 组
  "" 组
  Ancestors: "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "" 组
  "iDeal工作台" 文档
  "iDeal工作台" 窗口
  "iDeal工作台" 窗格
  "桌面" 窗格
  [ No Parent ]

能告诉我这些 UIA 特征都是什么意思吗

```

```
