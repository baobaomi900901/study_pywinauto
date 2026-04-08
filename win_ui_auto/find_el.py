import json
import re
import time
import uiautomation as auto
from highlight import HighlightWindow

TYPE_MAP = {
    "Window": auto.WindowControl,
    "Pane": auto.PaneControl,
    "Button": auto.ButtonControl,
    "ToolBar": auto.ToolBarControl,
    "Edit": auto.EditControl,
    "Text": auto.TextControl,
    "List": auto.ListControl,
    "ListItem": auto.ListItemControl,
    "ComboBox": auto.ComboBoxControl,
    "CheckBox": auto.CheckBoxControl,
    "RadioButton": auto.RadioButtonControl,
    "Menu": auto.MenuControl,
    "MenuItem": auto.MenuItemControl,
    "Tree": auto.TreeControl,
    "TreeItem": auto.TreeItemControl,
    "Tab": auto.TabControl,
    "TabItem": auto.TabItemControl,
    "ScrollBar": auto.ScrollBarControl,
    "Slider": auto.SliderControl,
    "ProgressBar": auto.ProgressBarControl,
    "Image": auto.ImageControl,
    "Hyperlink": auto.HyperlinkControl,
}

def parse_xpath(xpath_str):
    xpath_str = xpath_str.lstrip('/')
    steps = xpath_str.split('/')
    result = []
    for step in steps:
        if not step:
            continue
        match = re.match(r'^(\w+)(.*)$', step)
        if not match:
            raise ValueError(f"无法解析步骤: {step}")
        control_type_short = match.group(1)
        predicates = match.group(2).strip()
        attrs = {}
        position = None
        for block in re.findall(r'\[(.*?)\]', predicates):
            block = block.strip()
            if '=' in block:
                attr_match = re.match(r'@(\w+)=\'(.+)\'', block)
                if not attr_match:
                    attr_match = re.match(r'@(\w+)="(.+)"', block)
                if attr_match:
                    attr_name, attr_value = attr_match.groups()
                    attrs[attr_name] = attr_value
                else:
                    raise ValueError(f"无法解析属性条件: {block}")
            else:
                try:
                    position = int(block)
                except ValueError:
                    raise ValueError(f"无效的位置索引: {block}")
        result.append((control_type_short, attrs, position))
    return result

def find_control_by_steps(steps, timeout=3):
    root = auto.GetRootControl()
    current = root
    for idx, (ctrl_type_short, attrs, position) in enumerate(steps):
        ctrl_class = TYPE_MAP.get(ctrl_type_short)
        if ctrl_class is None:
            raise ValueError(f"不支持的控件类型: {ctrl_type_short}")
        start_time = time.time()
        found_control = None
        matched_controls = []  # 用于调试
        while time.time() - start_time < timeout:
            children = current.GetChildren()
            matched = []
            for child in children:
                child_type_short = child.ControlTypeName
                if child_type_short.endswith("Control"):
                    child_type_short = child_type_short[:-7]
                if child_type_short != ctrl_type_short:
                    continue
                match = True
                for attr_name, attr_value in attrs.items():
                    if attr_name == "ClassName":
                        if child.ClassName != attr_value:
                            match = False
                            break
                    elif attr_name == "Name":
                        if child.Name != attr_value:
                            match = False
                            break
                    elif attr_name == "AutomationId":
                        if child.AutomationId != attr_value:
                            match = False
                            break
                if match:
                    matched.append(child)
            if matched:
                matched_controls = matched  # 记录以便调试
                if position is not None:
                    if 1 <= position <= len(matched):
                        found_control = matched[position - 1]
                        break
                    else:
                        # 索引超出，打印警告但继续等待（可能后续会加载）
                        print(f"警告: 第 {idx+1} 步需要索引 {position}，但只找到 {len(matched)} 个匹配控件，等待重试...")
                        time.sleep(0.2)
                        continue
                else:
                    found_control = matched[0]
                    break
            time.sleep(0.1)
        if found_control is None:
            # 调试信息：打印所有匹配的子控件（即使不符合属性）
            print(f"\n第 {idx+1} 步未找到控件: {ctrl_type_short} 属性 {attrs} 索引 {position}")
            print("当前控件的子控件列表（类型、ClassName、Name）：")
            all_children = current.GetChildren()
            for i, child in enumerate(all_children):
                child_type = child.ControlTypeName
                print(f"  [{i}] {child_type} ClassName='{child.ClassName}' Name='{child.Name}'")
            if matched_controls:
                print(f"符合属性条件的控件有 {len(matched_controls)} 个，但索引 {position} 无效。")
                print("尝试使用第一个匹配的控件...")
                found_control = matched_controls[0]
            else:
                return None
        current = found_control
    return current

def main():
    try:
        with open("el.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("错误：未找到 el.json 文件，请先运行探查工具按 F8 生成。")
        return
    except Exception as e:
        print(f"读取 el.json 失败: {e}")
        return

    xpath = data.get("xpath")
    if not xpath:
        print("错误：el.json 中没有 xpath 字段。")
        return

    print(f"使用 XPath: {xpath}")

    try:
        steps = parse_xpath(xpath)
        print("解析步骤:", steps)
    except Exception as e:
        print(f"XPath 解析失败: {e}")
        return

    print("正在定位控件...")
    control = find_control_by_steps(steps, timeout=3)
    if control is None:
        print("未找到目标控件，请确保目标窗口存在且 XPath 正确。")
        return

    rect = control.BoundingRectangle
    if not rect or rect.width() <= 0 or rect.height() <= 0:
        print("控件位置无效。")
        return

    print(f"找到控件，位置: ({rect.left}, {rect.top}, {rect.width()}, {rect.height()})")
    highlight = HighlightWindow()
    time.sleep(0.5)
    highlight.update(rect.left, rect.top, rect.width(), rect.height())
    print("已在屏幕上高亮控件，按回车键退出...")
    input()
    highlight.clear()
    highlight.stop()
    print("已退出。")

if __name__ == "__main__":
    main()