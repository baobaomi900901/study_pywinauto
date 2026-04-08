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

def find_control_by_steps(steps, timeout=0.5):
    root = auto.GetRootControl()
    current = root
    for idx, (ctrl_type_short, attrs, position) in enumerate(steps):
        start_time = time.time()
        found_control = None
        matched_controls = []
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
                matched_controls = matched
                if position is not None:
                    if 1 <= position <= len(matched):
                        found_control = matched[position - 1]
                        break
                    else:
                        print(f"警告: 第 {idx+1} 步需要索引 {position}，实际找到 {len(matched)} 个，使用第一个匹配项。")
                        found_control = matched[0]
                        break
                else:
                    found_control = matched[0]
                    break
            time.sleep(0.02)
        if found_control is None:
            if matched_controls:
                found_control = matched_controls[0]
                print(f"使用第一个匹配控件继续（第{idx+1}步）")
            else:
                print(f"第 {idx+1} 步未找到任何匹配控件: {ctrl_type_short} 属性 {attrs}")
                return None
        current = found_control
    return current

def main():
    overall_start = time.time()

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

    parse_start = time.time()
    try:
        steps = parse_xpath(xpath)
        parse_elapsed = time.time() - parse_start
        print(f"XPath 解析耗时: {parse_elapsed:.3f} 秒")
        print("解析步骤:", steps)
    except Exception as e:
        print(f"XPath 解析失败: {e}")
        return

    print("正在定位控件...")
    locate_start = time.time()
    control = find_control_by_steps(steps, timeout=0.5)
    locate_elapsed = time.time() - locate_start
    if control is None:
        print(f"定位控件耗时: {locate_elapsed:.3f} 秒")
        print("未找到目标控件，请确保目标窗口存在且 XPath 正确。")
        return
    print(f"定位控件耗时: {locate_elapsed:.3f} 秒")

    top_window = control.GetTopLevelControl()
    if top_window and hasattr(top_window, 'SetActive'):
        print("正在激活窗口...")
        top_window.SetActive()
        time.sleep(0.05)   # 缩短延迟
    else:
        print("无法获取顶层窗口或不支持激活，跳过。")

    rect = control.BoundingRectangle
    if not rect or rect.width() <= 0 or rect.height() <= 0:
        print("控件位置无效。")
        return

    print(f"找到控件，位置: ({rect.left}, {rect.top}, {rect.width()}, {rect.height()})")

    highlight = HighlightWindow()
    time.sleep(0.2)   # 等待高亮窗口就绪（原0.5秒）
    highlight.update(rect.left, rect.top, rect.width(), rect.height())

    total_elapsed = time.time() - overall_start
    print(f"总耗时（到高亮显示）: {total_elapsed:.3f} 秒")
    print("已在屏幕上高亮控件，按回车键退出...")
    input()
    highlight.clear()
    highlight.stop()
    print("已退出。")

if __name__ == "__main__":
    main()