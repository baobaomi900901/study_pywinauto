import uiautomation as auto
import time

def get_edit_control(control):
    """递归查找并返回第一个 EditControl（输入框）"""
    if control.ControlType == auto.ControlType.EditControl:
        return control
    try:
        children = control.GetChildren()
    except:
        return None
    for child in children:
        result = get_edit_control(child)
        if result:
            return result
    return None

def get_buttons(control):
    """递归查找并返回所有 ButtonControl（按钮）的列表"""
    buttons = []
    def traverse(ctrl):
        if ctrl.ControlType == auto.ControlType.ButtonControl:
            buttons.append(ctrl)
        try:
            children = ctrl.GetChildren()
        except:
            children = []
        for child in children:
            traverse(child)
    traverse(control)
    return buttons

def get_dialog_type(dialog):
    """判断对话框类型：alert, confirm, prompt 或 unknown"""
    edit = get_edit_control(dialog)
    buttons = get_buttons(dialog)

    print(f"Debug: 找到 {len(buttons)} 个按钮, 存在输入框: {edit is not None}")
    for i, btn in enumerate(buttons, start=1):
        print(f"  按钮{i}: Name='{btn.Name}', ClassName='{btn.ClassName}'")
    if edit:
        print(f"  输入框: Name='{edit.Name}', ClassName='{edit.ClassName}'")

    if edit:
        return 'prompt'
    elif len(buttons) == 1:
        return 'alert'
    elif len(buttons) == 2:
        return 'confirm'
    else:
        return 'unknown'

def get_dialog_text(dialog):
    """提取对话框中所有可见的文本内容（如消息正文），排除对话框标题和交互控件的文本。"""
    collected_texts = []
    excluded_types = {
        auto.ControlType.ButtonControl,
        auto.ControlType.CheckBoxControl,
        auto.ControlType.RadioButtonControl,
        auto.ControlType.ComboBoxControl,
        auto.ControlType.ListControl,
        auto.ControlType.ListItemControl,
        auto.ControlType.TabControl,
        auto.ControlType.TreeControl,
        auto.ControlType.HyperlinkControl,
    }
    title = dialog.Name.strip()

    def traverse(ctrl, is_root=False):
        if not is_root and ctrl.Name and ctrl.ControlType not in excluded_types:
            text = ctrl.Name.strip()
            if text and text != title:
                collected_texts.append(text)
        try:
            children = ctrl.GetChildren()
        except:
            children = []
        for child in children:
            traverse(child, is_root=False)

    traverse(dialog, is_root=True)

    unique_texts = []
    seen = set()
    for text in collected_texts:
        if text not in seen:
            unique_texts.append(text)
            seen.add(text)

    return '\n'.join(unique_texts)

def get_button_intent_mapping():
    """
    返回按钮意图到可能的多语言文本的映射。
    键：用户可能输入的意图（如“确定”）
    值：该意图可能对应的按钮文本列表（包含常见的中英文及变体）
    """
    return {
        "确定": ["确定", "OK", "Yes", "确认", "Confirm", "Done"],
        "取消": ["取消", "Cancel", "No", "Abort", "Close"],
        "是": ["是", "Yes", "确定"],
        "否": ["否", "No", "取消"],
        # 可根据需要继续添加其他意图
    }

def main(title_base: str, input_content: str, click_btn: str) -> dict:
    """
    主函数：根据标题基础定位对话框，判断类型，输入内容（如果是prompt），并点击指定按钮。
    支持国际化按钮匹配：传入“确定”可匹配“OK”、“Yes”等；传入“取消”可匹配“Cancel”、“No”等。
    """
    dialog_name = f"{title_base} 显示"
    print(f"目标窗口标题：{dialog_name}")

    dialog = auto.WindowControl(Name=dialog_name)
    if not dialog.Exists():
        print("false")
        return {"success": False, "dialog_type": None, "dialog_text": "", "message": "对话框不存在"}

    print("true")
    dlg_type = get_dialog_type(dialog)
    print(f"对话框类型：{dlg_type}")

    # 提取对话框正文
    message_text = get_dialog_text(dialog)
    if message_text:
        print("对话框正文内容：")
        print(message_text)
    else:
        print("未提取到正文文本")
        message_text = ""

    # 如果是 prompt，在输入框中输入内容
    if dlg_type == 'prompt':
        edit = get_edit_control(dialog)
        if edit:
            print(f"在输入框中输入内容：{input_content}")
            edit.Click()
            time.sleep(0.2)
            edit.SendKeys('{Ctrl}a')
            edit.SendKeys('{Delete}')
            edit.SendKeys(input_content)
        else:
            print("警告：prompt 类型但未找到输入框")

    # 查找并点击指定按钮（支持国际化）
    buttons = get_buttons(dialog)
    target_button = None

    # 获取意图映射
    intent_map = get_button_intent_mapping()
    if click_btn in intent_map:
        possible_texts = intent_map[click_btn]  # 使用映射的多语言列表
    else:
        possible_texts = [click_btn]            # 直接使用原文本

    # 遍历按钮，检查按钮名称是否包含任一可能的文本（忽略大小写）
    for btn in buttons:
        btn_name = btn.Name.lower()
        for text in possible_texts:
            if text.lower() in btn_name:
                target_button = btn
                break
        if target_button:
            break

    if target_button:
        button_name = target_button.Name  # 在点击前保存名称
        print(f"点击按钮：{button_name}")
        target_button.Click()
        return {
            "success": True,
            "dialog_type": dlg_type,
            "dialog_text": message_text,
            "message": f"成功点击按钮 '{button_name}'"
        }
    else:
        print(f"未找到匹配的按钮（尝试匹配：{possible_texts}）")
        return {
            "success": False,
            "dialog_type": dlg_type,
            "dialog_text": message_text,
            "message": f"未找到匹配的按钮（尝试匹配：{possible_texts}）"
        }
    

if __name__ == "__main__":
    # 示例调用，并打印返回的摘要信息
    result = main("127.0.0.1:5500", "唐清伟", "确定")
    print("\n=== 操作结果摘要 ===")
    print(f"成功: {result['success']}")
    print(f"对话框类型: {result['dialog_type']}")
    print(f"对话框正文: {result['dialog_text']}")
    print(f"消息: {result['message']}")