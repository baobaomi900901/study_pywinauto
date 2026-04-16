# win_ui_auto/hooks/get.py
import sys
import json
import uiautomation as auto
from hooks.locator import locate_by_xpath

def get_element_text_smart(el):
    """智能提取单个元素的文本：Value 优先于 Name"""
    name = (el.Name or "").strip()
    value = ""
    try:
        if auto.PatternId.ValuePattern in el.GetSupportedPatterns():
            value = (el.GetValuePattern().Value or "").strip()
    except:
        pass
    # 逻辑：如果 Value 存在且长度大于等于 Name，取 Value；否则取 Name
    return value if len(value) >= len(name) else name

def extract_recursive(el, max_deep, current_deep=0, visited_texts=None):
    """递归遍历子级并提取文本"""
    if visited_texts is None:
        visited_texts = []
    
    if current_deep > max_deep:
        return visited_texts

    txt = get_element_text_smart(el)
    # 去重且排除空字符串
    if txt and txt not in visited_texts:
        visited_texts.append(txt)

    try:
        # 获取所有子控件进行深度遍历
        children = el.GetChildren()
        for child in children:
            extract_recursive(child, max_deep, current_deep + 1, visited_texts)
    except:
        pass
        
    return visited_texts

def run(xpath, timeout=10.0, get_type="full", deep=0):
    target = locate_by_xpath(xpath, timeout)
    
    if not target:
        print("\n❌ 最终结果：未找到目标元素。")
        sys.exit(1)

    if get_type == "text":
        # 递归提取所有文本
        text_list = extract_recursive(target, deep)
        
        # --- 核心修改：以 [str1, str2...] 格式打印 ---
        print("\n✅ 提取到的文本列表:")
        # 使用 json.dumps 确保输出是一个合法的 JSON 数组字符串，方便跨语言调用
        print(json.dumps(text_list, ensure_ascii=False))
        # ------------------------------------------
        
        return text_list
    
    else:
        # 保持原有的 full 模式不变
        rect = target.BoundingRectangle
        position = [rect.left, rect.top, rect.width(), rect.height()] if rect else []
        
        info = {
            "ControlType": target.ControlTypeName,
            "ClassName": target.ClassName,
            "Name": target.Name,
            "position": position,
            "Value": get_element_text_smart(target),
            "HelpText": target.HelpText,
            "IsPassword": getattr(target, 'IsPassword', False),
            "automation_type": "UIA"
        }
        
        print("\n✅ 目标元素获取成功：")
        print(json.dumps(info, indent=4, ensure_ascii=False))
        return info
