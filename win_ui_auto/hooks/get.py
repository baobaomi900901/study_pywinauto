# win_ui_auto/hooks/get.py
import sys
import json
import time
import uiautomation as auto
from hooks.locator import locate_by_xpath
from constants import DEBUG

def get_element_text_smart(el):
    """
    智能提取控件文本：
    1. LegacyIAccessiblePattern（MSAA，适用于记事本 RichEdit）
    2. ValuePattern（标准 UIA）
    3. WindowText（Win32 底层）
    4. Name（最终保底）
    """
    # 1. MSAA 桥接（直接尝试，不检查 SupportedPatterns）
    try:
        legacy = el.GetLegacyIAccessiblePattern()
        if legacy:
            val = legacy.Value
            if val and val.strip():
                return val.strip()
    except:
        pass

    # 2. UIA ValuePattern（同样直接尝试）
    try:
        value_pattern = el.GetValuePattern()
        if value_pattern:
            value = value_pattern.Value
            if value and value.strip():
                return value.strip()
    except:
        pass

    # 3. Win32 窗口文本
    try:
        hwnd = el.NativeWindowHandle
        if hwnd:
            import ctypes
            user32 = ctypes.windll.user32
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                text = buf.value
                if text and text.strip():
                    return text.strip()
    except:
        pass

    # 4. 保底：Name
    return (el.Name or "").strip()

def extract_recursive(el, max_deep, current_deep=0, visited_texts=None):
    """递归遍历子级并提取文本"""
    if visited_texts is None:
        visited_texts = []
    
    if current_deep > max_deep:
        return visited_texts

    txt = get_element_text_smart(el)
    if txt and txt not in visited_texts:
        visited_texts.append(txt)

    try:
        for child in el.GetChildren():
            extract_recursive(child, max_deep, current_deep + 1, visited_texts)
    except:
        pass
        
    return visited_texts

def run(xpath, timeout=10.0, get_type="full", deep=0):
    target = locate_by_xpath(xpath, timeout)

    if not target:
        if DEBUG:
            print("\n❌ 最终结果：未找到目标元素。")
        sys.exit(1)
        
    if DEBUG:
        # ---------- 诊断开始 ----------
        print("\n[诊断] 定位到的控件详情：")
        print(f"  ControlType: {target.ControlTypeName}")
        print(f"  ClassName: {target.ClassName}")
        print(f"  Name: {target.Name}")
        print(f"  AutomationId: {target.AutomationId}")
        print(f"  IsKeyboardFocusable: {target.IsKeyboardFocusable}")
        print(f"  IsEnabled: {target.IsEnabled}")
        print(f"  BoundingRectangle: {target.BoundingRectangle}")
        print(f"  NativeWindowHandle: {target.NativeWindowHandle}")
    
        # 强制尝试多种方式获取文本
        val_methods = {}
        try:
            val_methods['ValuePattern'] = target.GetValuePattern().Value if target.GetValuePattern() else None
        except: val_methods['ValuePattern'] = '异常'
        try:
            val_methods['LegacyIAccessible'] = target.GetLegacyIAccessiblePattern().Value if target.GetLegacyIAccessiblePattern() else None
        except: val_methods['LegacyIAccessible'] = '异常'
        try:
            import ctypes
            hwnd = target.NativeWindowHandle
            if hwnd:
                buf = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
                val_methods['WindowText'] = buf.value
        except: val_methods['WindowText'] = '异常'

        print(f"  各方式获取的文本: {val_methods}")
    # ---------- 诊断结束 ----------
    
    if not target:
        if DEBUG:
            print("\n❌ 最终结果：未找到目标元素。")
        sys.exit(1)

    # 🔥 关键修复：强制激活目标控件所在的顶层窗口
    try:
        top_window = target.GetTopLevelControl()
        if top_window and top_window.NativeWindowHandle:
            import ctypes
            user32 = ctypes.windll.user32
            # 将窗口设为前台并给予焦点
            user32.SetForegroundWindow(top_window.NativeWindowHandle)
            time.sleep(0.2)  # 等待窗口完全激活
            target.Refresh()  # 再次刷新控件状态
    except:
        pass

    if get_type == "text":
        text_list = extract_recursive(target, deep)
        if DEBUG:
            print("\n✅ 提取到的文本列表:")
        print(json.dumps(text_list, ensure_ascii=False))
        return text_list
    
    else:
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
        if DEBUG:
            print("\n✅ 目标元素获取成功：")
        print(json.dumps(info, indent=4, ensure_ascii=False))
        return info
