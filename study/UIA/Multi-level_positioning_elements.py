import uiautomation as auto
import tkinter as tk
from typing import Optional, Tuple, Dict, Any, List

# ========== 1. 辅助函数：单层控件查找 ==========
def _find_control(root_control: auto.Control, properties: Dict[str, Any], timeout: float) -> Optional[auto.Control]:
    """在 root_control 下查找匹配 properties 的控件，支持 foundIndex 指定第几个匹配"""
    props = properties.copy()
    # 提取 foundIndex（默认 1），并从 props 中移除，避免作为属性传递
    found_index = props.pop('foundIndex', 1)

    # 处理 ControlType 字符串 → 枚举
    if 'ControlType' in props:
        ct = props['ControlType']
        if isinstance(ct, str):
            control_map = {
                'Button': auto.ControlType.ButtonControl,
                'Edit': auto.ControlType.EditControl,
                'Text': auto.ControlType.TextControl,
                'Window': auto.ControlType.WindowControl,
                'Pane': auto.ControlType.PaneControl,
                'CheckBox': auto.ControlType.CheckBoxControl,
                'ComboBox': auto.ControlType.ComboBoxControl,
                'List': auto.ControlType.ListControl,
                'ListItem': auto.ControlType.ListItemControl,
                'Menu': auto.ControlType.MenuControl,
                'MenuItem': auto.ControlType.MenuItemControl,
                'ToolBar': auto.ControlType.ToolBarControl,
                'Tab': auto.ControlType.TabControl,
                'TabItem': auto.ControlType.TabItemControl,
                'Tree': auto.ControlType.TreeControl,
                'TreeItem': auto.ControlType.TreeItemControl,
                'ScrollBar': auto.ControlType.ScrollBarControl,
                'Slider': auto.ControlType.SliderControl,
                'Spinner': auto.ControlType.SpinnerControl,
                'ProgressBar': auto.ControlType.ProgressBarControl,
                'Separator': auto.ControlType.SeparatorControl,
                'Hyperlink': auto.ControlType.HyperlinkControl,
                'Image': auto.ControlType.ImageControl,
                'Document': auto.ControlType.DocumentControl,
                'Group': auto.ControlType.GroupControl,
                'Thumb': auto.ControlType.ThumbControl,
                'DataGrid': auto.ControlType.DataGridControl,
                'DataItem': auto.ControlType.DataItemControl,
                'Header': auto.ControlType.HeaderControl,
                'HeaderItem': auto.ControlType.HeaderItemControl,
                'Table': auto.ControlType.TableControl,
                'TitleBar': auto.ControlType.TitleBarControl,
                'MenuBar': auto.ControlType.MenuBarControl,
                'StatusBar': auto.ControlType.StatusBarControl,
            }
            if ct in control_map:
                props['ControlType'] = control_map[ct]
            else:
                try:
                    props['ControlType'] = getattr(auto.ControlType, f"{ct}Control")
                except AttributeError:
                    print(f"警告：未知控件类型 '{ct}'，将忽略 ControlType 条件")
                    del props['ControlType']

    # 使用 timeout 和 foundIndex 查找
    try:
        control = root_control.Control(**props, timeout=timeout, foundIndex=found_index)
        return control if control.Exists else None
    except Exception as e:
        print(f"查找控件失败: {e}")
        return None

# ========== 2. 辅助函数：检查控件是否匹配属性 ==========
def _match_control(control: auto.Control, properties: Dict[str, Any]) -> bool:
    """检查控件是否匹配给定的属性字典（用于根控件匹配）"""
    # 忽略 foundIndex（仅用于查找，不用于匹配）
    props = {k: v for k, v in properties.items() if k != 'foundIndex'}

    for key, value in props.items():
        if key == 'ControlType' and isinstance(value, str):
            # 将字符串转换为枚举进行比较
            control_map = {
                'Button': auto.ControlType.ButtonControl,
                'Edit': auto.ControlType.EditControl,
                'Text': auto.ControlType.TextControl,
                'Window': auto.ControlType.WindowControl,
                'Pane': auto.ControlType.PaneControl,
                'CheckBox': auto.ControlType.CheckBoxControl,
                'ComboBox': auto.ControlType.ComboBoxControl,
                'List': auto.ControlType.ListControl,
                'ListItem': auto.ControlType.ListItemControl,
                'Menu': auto.ControlType.MenuControl,
                'MenuItem': auto.ControlType.MenuItemControl,
                'ToolBar': auto.ControlType.ToolBarControl,
                'Tab': auto.ControlType.TabControl,
                'TabItem': auto.ControlType.TabItemControl,
                'Tree': auto.ControlType.TreeControl,
                'TreeItem': auto.ControlType.TreeItemControl,
                'ScrollBar': auto.ControlType.ScrollBarControl,
                'Slider': auto.ControlType.SliderControl,
                'Spinner': auto.ControlType.SpinnerControl,
                'ProgressBar': auto.ControlType.ProgressBarControl,
                'Separator': auto.ControlType.SeparatorControl,
                'Hyperlink': auto.ControlType.HyperlinkControl,
                'Image': auto.ControlType.ImageControl,
                'Document': auto.ControlType.DocumentControl,
                'Group': auto.ControlType.GroupControl,
                'Thumb': auto.ControlType.ThumbControl,
                'DataGrid': auto.ControlType.DataGridControl,
                'DataItem': auto.ControlType.DataItemControl,
                'Header': auto.ControlType.HeaderControl,
                'HeaderItem': auto.ControlType.HeaderItemControl,
                'Table': auto.ControlType.TableControl,
                'TitleBar': auto.ControlType.TitleBarControl,
                'MenuBar': auto.ControlType.MenuBarControl,
                'StatusBar': auto.ControlType.StatusBarControl,
            }
            expected = control_map.get(value)
            if expected is None:
                try:
                    expected = getattr(auto.ControlType, f"{value}Control")
                except AttributeError:
                    return False
            if control.ControlType != expected:
                return False
        else:
            if getattr(control, key, None) != value:
                return False
    return True

# ========== 3. 核心函数：层级路径定位 ==========
def locate_element_by_path(
    hwnd: int,
    path: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 3.0
) -> Optional[Tuple[int, int, int, int]]:
    """
    通过窗口句柄和层级路径定位元素，返回其在屏幕上的坐标和尺寸。
    - 若 path 为 None 或空列表，返回主窗口自身的矩形。
    - 若 path 非空，则按以下规则处理：
        * 如果 path 的第一个元素匹配主窗口自身，则从主窗口开始，后续元素依次查找子控件。
        * 否则，从主窗口的子控件开始查找（原逻辑）。
    """
    root = auto.ControlFromHandle(hwnd)
    if not root:
        print(f"无法获取句柄 {hex(hwnd)} 的 UIA 根控件")
        return None

    # 空路径：返回主窗口
    if not path:
        rect = root.BoundingRectangle
        return (rect.left, rect.top, rect.width(), rect.height())

    # 检查第一层是否匹配主窗口自身
    if _match_control(root, path[0]):
        # 如果只有一层，直接返回主窗口坐标
        if len(path) == 1:
            rect = root.BoundingRectangle
            return (rect.left, rect.top, rect.width(), rect.height())
        # 从第二层开始向下查找子控件
        current = root
        for i, props in enumerate(path[1:], start=1):
            control = _find_control(current, props, timeout)
            if not control:
                print(f"未找到控件 (层级 {i+1})")
                return None
            if i == len(path) - 1:
                rect = control.BoundingRectangle
                return (rect.left, rect.top, rect.width(), rect.height())
            current = control
        return None
    else:
        # 原逻辑：从主窗口的子控件开始查找
        current = root
        for i, props in enumerate(path):
            control = _find_control(current, props, timeout)
            if not control:
                print(f"未找到控件 (层级 {i+1})")
                return None
            if i == len(path) - 1:
                rect = control.BoundingRectangle
                return (rect.left, rect.top, rect.width(), rect.height())
            current = control
        return None

# ========== 4. 辅助函数：绘制红框验证 ==========
def show_red_rect(x: int, y: int, width: int, height: int, duration: float = 2.0):
    """在屏幕上绘制红色矩形框，并在终端显示倒计时"""
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.attributes('-transparentcolor', 'white')
    root.configure(bg='white')
    root.geometry(f"{width}x{height}+{x}+{y}")

    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0, bg='white')
    canvas.pack()
    canvas.create_rectangle(0, 0, width, height, outline='red', width=4, fill='')

    remaining = duration
    def countdown():
        nonlocal remaining
        if remaining > 0:
            print(f"倒计时: {remaining:.1f} 秒", end='\r')
            remaining -= 0.1
            root.after(100, countdown)
        else:
            print("倒计时结束", end='\n')
            root.destroy()
    countdown()
    root.mainloop()

# ========== 使用示例 ==========
if __name__ == '__main__':
    hwnd = 0x261662

    # 特征2：使用稳定属性 + foundIndex 指定第二个 TTBXDock
    path_button = [
        {'ControlType': 'Window', 'ClassName': 'TScpCommanderForm'},
        {'ControlType': 'Pane', 'ClassName': 'TPanel'},           # 第二层
        {'ControlType': 'Pane', 'ClassName': 'TTBXDock', 'foundIndex': 2},  # 第三层，取第二个
        # {'ControlType': 'ToolBar', 'Name': '本地选择'},           # 第四层
        # {'ControlType': 'Button', 'Name': '选择文件'}            # 第五层
    ]

    result2 = locate_element_by_path(hwnd, path_button, timeout=3.0)
    if result2:
        x2, y2, w2, h2 = result2
        print(f"按钮位置: ({x2}, {y2}), 尺寸: {w2} x {h2}")
        show_red_rect(x2, y2, w2, h2, duration=3)
    else:
        print("未找到按钮")



    # 特征1:
    # path_button = [
    #     {'ControlType': 'Window', 'ClassName': 'TScpCommanderForm'},
    #     {'AutomationId': '660878', 'ControlType': 'Pane'},
    #     {'AutomationId': '919894', 'ControlType': 'Pane'},
    #     {'Name': '本地选择', 'ControlType': 'ToolBar'},
    #     {'Name': '选择文件', 'ControlType': 'Button'}
    # ]