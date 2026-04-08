# 说明

基于 `uiautomation` 和 `pynput` 的 Windows 界面控件信息获取工具。无需管理员权限，鼠标悬停即可高亮控件，按 `F8` 打印完整控件信息（含父级链、进程名等），方便自动化脚本开发。

## 功能特点

- 鼠标悬停 0.8 秒 → 红色高亮框显示当前控件
- 按 `F8` 键 → 输出控件完整 JSON 信息（类型、名称、位置、Value、父级链、所属进程等）
- 无需管理员权限，安全无干扰
- 支持探查模式开关，可随时开启/关闭

## 目录结构

```
win_ui_auto/
├── main.py # 程序入口，解析命令行/交互命令
├── constants.py # 配置常量（HOVER_DELAY, CLEAR_DELAY 等）
├── highlight.py # 高亮窗口（Tkinter 实现）
├── control_info.py # 控件信息获取（\_get_deepest_control, \_get_control_info, \_print_control_info）
├── process_utils.py # 进程名获取（get_process_name）
├── listeners.py # 键盘和鼠标监听（pynput 回调）
└── probe.py # UIProbe 核心类，组装各模块并管理线程
```

## 安装依赖

```
pip install uiautomation pynput
```

## 使用方式

1. 进入项目目录

2. 运行程序

   ```
   py main.py
   ```

3. 交互命令

   ```
   1 – 开启探查模式
   2 – 关闭探查模式
   clear – 清除当前高亮框
   wq – 退出程序
   ```

4. 探查步骤
   - 输入 1 开启探查模式

   - 移动鼠标到任意目标控件上，停留 0.8 秒，控件周围出现红色高亮框

   - 按下键盘 F8 键，控制台会打印该控件的详细 JSON 信息（包括父级链和应用进程）

   - 可重复移动鼠标到不同控件，按 F8 获取信息

## 输出示例

```
[UI 信息]
{
  "ControlType": "ButtonControl",
  "ClassName": "",
  "Name": "选择文件",
  "position": [533, 556, 27, 26],
  "Value": "",
  "HelpText": "",
  "IsPassword": false,
  "index": 0,
  "same_type_index": 0,
  "parent": [
    { "ControlType": "PaneControl", "ClassName": "#32769", "is_desktop": true },
    { "ControlType": "WindowControl", "ClassName": "TScpCommanderForm", "is_app": true },
    ...
  ],
  "application": { "pid": 12240, "name": "WinSCP.exe" }
}
```
