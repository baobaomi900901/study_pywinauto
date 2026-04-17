# win_ui_auto/hooks/get.py
import sys
import json
import time
import os
import uiautomation as auto
from hooks.locator import locate_by_xpath
from constants import DEBUG
from control_info import get_control_info

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
    # 确保在 UIA 初始化线程环境里取 Pattern/属性，避免 ValuePattern 等在部分场景取值异常
    with auto.UIAutomationInitializerInThread():
        target = locate_by_xpath(xpath, timeout)

        if not target:
            if DEBUG:
                print("\n❌ 最终结果：未找到目标元素。")
            sys.exit(1)

        # 统一信息采集口径：与 --find 保持一致，复用 control_info.get_control_info
        rect = None
        try:
            rect = target.BoundingRectangle
        except Exception:
            rect = None

        x = y = None
        if rect:
            x = rect.left + rect.width() // 2
            y = rect.top + rect.height() // 2

        # get_control_info 需要 current_pid 用于过滤“自身高亮窗口”；--get 场景下无高亮窗口，传当前进程 pid 即可
        base_info = None
        try:
            if x is not None and y is not None:
                base_info = get_control_info(target, x, y, os.getpid())
        except Exception:
            base_info = None
        
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
            # 与 --find 同口径：优先输出 get_control_info 的结果；失败时再回退到简化信息
            if base_info:
                info = base_info
            else:
                rect2 = None
                try:
                    rect2 = target.BoundingRectangle
                except Exception:
                    rect2 = None
                position = [rect2.left, rect2.top, rect2.width(), rect2.height()] if rect2 else []
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
