import re
import time
import uiautomation as auto

# 类型映射（短名 -> uiautomation 控件类）
TYPE_MAP = {
    "Window": auto.WindowControl,
    "Pane": auto.PaneControl,
    "Button": auto.ButtonControl,
    "ToolBar": auto.ToolBarControl,
    "Edit": auto.EditControl,
    "Text": auto.TextControl,
    "Document": auto.DocumentControl,
    "Group": auto.GroupControl,
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
    """
    解析简化 XPath，返回步骤列表。
    步骤格式：(control_type, {attr:value}, position)
    """
    xpath_str = xpath_str.lstrip('/')
    steps = xpath_str.split('/')
    result = []
    for step in steps:
        if not step:
            continue
        match = re.match(r'^(\w+)(.*)$', step)
        if not match:
            raise ValueError(f"无法解析步骤: {step}")
        control_type = match.group(1)
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
        result.append((control_type, attrs, position))
    return result

def locate_control_by_steps(steps, timeout=2):
    """
    根据步骤列表定位控件，返回控件对象或 None。
    """
    root = auto.GetRootControl()
    current = root
    for idx, (ctrl_type, attrs, position) in enumerate(steps):
        start_time = time.time()
        found = None
        while time.time() - start_time < timeout:
            children = current.GetChildren()
            matched = []
            for child in children:
                # 检查控件类型
                child_type_short = child.ControlTypeName
                if child_type_short.endswith("Control"):
                    child_type_short = child_type_short[:-7]
                if child_type_short != ctrl_type:
                    continue
                # 检查属性
                ok = True
                for attr_name, attr_value in attrs.items():
                    if attr_name == "ClassName":
                        if child.ClassName != attr_value:
                            ok = False
                            break
                    elif attr_name == "Name":
                        if child.Name != attr_value:
                            ok = False
                            break
                    elif attr_name == "AutomationId":
                        if child.AutomationId != attr_value:
                            ok = False
                            break
                if ok:
                    matched.append(child)
            if matched:
                if position is not None and 1 <= position <= len(matched):
                    found = matched[position - 1]
                else:
                    found = matched[0]  # 取第一个
                break
            time.sleep(0.05)
        if found is None:
            print(f"定位失败：第 {idx+1} 步未找到控件 {ctrl_type} {attrs}")
            return None
        current = found
    return current

def collect_texts_from_control(control, include_hidden=False):
    """
    从指定控件开始，递归收集所有可见文本信息。
    返回列表，每个元素为 (控件类型, 文本内容)
    """
    texts = []

    def traverse(ctrl, depth=0):
        # 获取控件自身的文本
        text_content = None
        ctrl_type = ctrl.ControlTypeName

        # 优先取 Name，其次取 Value（针对 Edit 等）
        if ctrl.Name and ctrl.Name.strip():
            text_content = ctrl.Name.strip()
        else:
            try:
                val_pattern = ctrl.GetValuePattern()
                if val_pattern and val_pattern.Value:
                    text_content = val_pattern.Value.strip()
            except:
                pass

        if text_content:
            texts.append((ctrl_type, text_content))

        # 递归子控件
        for child in ctrl.GetChildren():
            if not include_hidden:
                # 简单检查是否可见（通过 BoundingRectangle 宽高>0）
                rect = child.BoundingRectangle
                if rect and rect.width() > 0 and rect.height() > 0:
                    traverse(child, depth+1)
            else:
                traverse(child, depth+1)

    traverse(control)
    return texts

def get_all_texts_by_xpath(xpath_str, timeout=2, include_hidden=False):
    """
    根据 XPath 定位控件，返回该控件下所有文本信息。
    :param xpath_str: XPath 字符串（简化格式）
    :param timeout: 定位超时时间（秒）
    :param include_hidden: 是否包含隐藏控件（默认只获取可见控件）
    :return: 文本列表，格式 [(控件类型, 文本), ...]
    """
    steps = parse_xpath(xpath_str)
    control = locate_control_by_steps(steps, timeout)
    if control is None:
        print("无法定位控件")
        return []
    texts = collect_texts_from_control(control, include_hidden)
    return texts

# ========== 使用示例 ==========
if __name__ == "__main__":
    xpath = "//Pane[@ClassName='Chrome_WidgetWin_1'][3]/Document[@ClassName='Chrome_RenderWidgetHostHWND'][1]/Group[1]/Group[2]/Group[1]/Group[2]/Group[1]/Group[1]/Group[2]/Group[2]/Group[1]/Group[1]/Group[1]/Group[2]/Group[1]/Group[1]/Group[1]/Group[3]/Group[1]/Group[2]/Group[1]"
    all_texts = get_all_texts_by_xpath(xpath, timeout=2)
    print(f"共获取 {len(all_texts)} 条文本：")
    for ctrl_type, text in all_texts:
        print(f"[{ctrl_type}] {text}")