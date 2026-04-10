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
