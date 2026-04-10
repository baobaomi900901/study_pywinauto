# win_ui_auto/hooks/set_act.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import re
import time
import msvcrt
import fnmatch
import ctypes
from ctypes import wintypes
import uiautomation as auto
from highlight import HighlightWindow

def get_all_render_hwnds():
    """Win32 API 全局扫描：找出系统里所有属于 Chrome 架构的真实渲染底板"""
    user32 = ctypes.windll.user32
    hwnds = []

    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "Chrome_RenderWidgetHostHWND":
            hwnds.append(h)
        return True

    def enum_top_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "Chrome_WidgetWin_1":
            user32.EnumChildWindows(h, ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_child_proc), 0)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_top_proc), 0)
    return list(set(hwnds))

def force_wake_up_chromium(hwnd=None, broadcast=False):
    """【核心绝杀】：索要 COM 接口，防沉睡"""
    user32 = ctypes.windll.user32
    target_hwnds = []
    
    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "Chrome_RenderWidgetHostHWND":
            target_hwnds.append(h)
        return True

    EnumChildProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    if broadcast:
        def enum_top_proc(h, lParam):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, buf, 256)
            if buf.value == "Chrome_WidgetWin_1":
                user32.EnumChildWindows(h, EnumChildProcType(enum_child_proc), 0)
            return True
        EnumTopProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumTopProcType(enum_top_proc), 0)
    elif hwnd:
        target_hwnds.append(hwnd)
        user32.EnumChildWindows(hwnd, EnumChildProcType(enum_child_proc), 0)

    try:
        oleacc = ctypes.windll.oleacc
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
        IID_IAccessible = GUID(0x618736e0, 0x3c3d, 0x11cf, (0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71))
        OBJID_CLIENT = -4
        for t_hwnd in set(target_hwnds):
            pacc = ctypes.c_void_p()
            oleacc.AccessibleObjectFromWindow(t_hwnd, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pacc))
    except: pass

def parse_xpath(xpath_str):
    xpath_str = xpath_str.lstrip('/')
    steps = xpath_str.split('/')
    result = []
    for step in steps:
        if not step: continue
        match = re.match(r'^(\w+)(.*)$', step)
        if not match: raise ValueError(f"无法解析步骤: {step}")
        control_type = match.group(1)
        predicates = match.group(2).strip()
        attrs = {}
        position = None
        for block in re.findall(r'\[(.*?)\]', predicates):
            block = block.strip()
            if '=' in block:
                attr_match = re.match(r'@(\w+)=\'(.+)\'', block) or re.match(r'@(\w+)="(.+)"', block)
                if attr_match:
                    k, v = attr_match.groups()
                    attrs[k] = v
            else:
                try: position = int(block)
                except: pass
        result.append((control_type, attrs, position))
    return result

def locate_lightning(steps, timeout=10):
    render_hwnds = get_all_render_hwnds()
    if not render_hwnds:
        print("[闪电战] 未找到 Chromium 渲染底板，请确认界面已开启。", file=sys.stderr)
        return None

    doc_index = -1
    for i, step in enumerate(steps):
        if step[0] == "Document":
            doc_index = i
            break
            
    if doc_index == -1:
        print("[闪电战] XPath 中未包含 Document 层。", file=sys.stderr)
        return None
        
    virtual_steps = steps[doc_index + 1:]
    print(f"[闪电战] 锁定 {len(render_hwnds)} 个渲染器。准备下潜 {len(virtual_steps)} 层寻址容器...", file=sys.stderr)
    
    start_time = time.time()
    attempts = 0
    
    while time.time() - start_time < timeout:
        attempts += 1
        for hwnd in render_hwnds:
            force_wake_up_chromium(hwnd)
            try:
                current = auto.ControlFromHandle(hwnd)
                success = True
                
                for ctrl_type, attrs, position in virtual_steps:
                    children = current.GetChildren()
                    matched = []
                    
                    for child in children:
                        ctype = child.ControlTypeName
                        if ctype.endswith("Control"): ctype = ctype[:-7]
                        if ctype != ctrl_type and ctrl_type != "*": continue
                        
                        ok = True
                        for k, v in attrs.items():
                            if k == 'ClassName' and child.ClassName != v: ok = False; break
                            if k == 'Name' and child.Name != v: ok = False; break
                            if k == 'AutomationId' and child.AutomationId != v: ok = False; break
                        if ok: matched.append(child)
                        
                    target_idx = (position - 1) if position else 0
                    if target_idx < len(matched):
                        current = matched[target_idx]
                    else:
                        success = False
                        break 
                        
                if success:
                    cost_time = time.time() - start_time
                    print(f"[闪电战] 容器击穿成功！耗时: {cost_time:.2f}秒 (冲锋次数: {attempts})", file=sys.stderr)
                    return current
            except Exception:
                pass
                
        time.sleep(0.1)
        
    print("\n[闪电战] 超时：渲染树未能在此时间内生成容器。", file=sys.stderr)
    return None

def find_all_controls_by_text(container, text, timeout=2, control_type=None):
    use_wildcard = '*' in text or '?' in text
    matches = []

    def name_matches(name):
        if not name: return False
        if use_wildcard:
            return fnmatch.fnmatch(name.lower(), text.lower())
        else:
            return text in name

    print(f"开始在容器内搜寻文字: '{text}' ...")
    end_time = time.time() + timeout
    
    while time.time() < end_time:
        force_wake_up_chromium(broadcast=True)
        for child in container.GetChildren():
            if control_type is not None and child.ControlTypeName != control_type:
                continue
            if name_matches(child.Name):
                matches.append(child)
                
        if matches: break
        
        def search_descendants(parent, depth):
            results = []
            if depth <= 0: return results
            for child in parent.GetChildren():
                if control_type is not None and child.ControlTypeName != control_type:
                    continue
                if name_matches(child.Name):
                    results.append(child)
                results.extend(search_descendants(child, depth-1))
            return results
            
        matches = search_descendants(container, 3)
        if matches: break
        
        time.sleep(0.1)
        
    return matches

def highlight_controls(controls):
    if not controls:
        return False
    highlights = []
    for ctrl in controls:
        rect = ctrl.BoundingRectangle
        if rect and rect.width() > 0 and rect.height() > 0:
            hl = HighlightWindow()
            time.sleep(0.05)
            hl.update(rect.left, rect.top, rect.width(), rect.height())
            highlights.append(hl)
            
    print("按回车键立即退出所有高亮，或等待10秒自动退出...")
    start_time = time.time()
    while time.time() - start_time < 10:
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b'\r', b'\n'):
                break
        time.sleep(0.2)
        
    for hl in highlights:
        hl.clear()
        hl.stop()
    return True

# =========================================================
# 核心大招：核弹级点击 (三层穿透)
# =========================================================
def click_control(ctrl):
    """三层穿透点击：内存Invoke -> 内存DoDefaultAction -> 强制焦点物理点击"""
    print(f"尝试点击控件: {ctrl.Name} (类型: {ctrl.ControlTypeName})...")

    # 1. 尝试 UIA 标准的纯内存触发（最稳定，无视被遮挡和焦点）
    try:
        invoke_pattern = ctrl.GetInvokePattern()
        if invoke_pattern:
            invoke_pattern.Invoke()
            print(" -> [成功] 已通过内存 InvokePattern 触发动作！")
            return True
    except Exception:
        pass

    # 2. 尝试 MSAA 兼容模式的纯内存触发（部分 Electron 按钮支持这个）
    try:
        legacy_pattern = ctrl.GetLegacyIAccessiblePattern()
        if legacy_pattern:
            legacy_pattern.DoDefaultAction()
            print(" -> [成功] 已通过内存 LegacyIAccessible 触发动作！")
            return True
    except Exception:
        pass

    # 3. 终极托底：物理模拟鼠标点击
    try:
        # 【极其重要】：点之前，强行把宿主窗口拉到最前，防止焦点被控制台吃掉！
        top_window = ctrl.GetTopLevelControl()
        if top_window:
            top_window.SwitchToThisWindow()
            time.sleep(0.1) # 等待窗口弹出

        # 关闭 simulateMove 的动画，直接闪现过去点击
        ctrl.Click(simulateMove=False)
        print(" -> [成功] 已通过物理鼠标强制点击！")
        return True
    except Exception as e:
        print(f" -> [失败] 所有点击手段均被阻隔: {e}", file=sys.stderr)
        return False
# =========================================================

def run(xpath, button_text, click=False, highlight=False, timeout=10, index=None):
    try:
        steps = parse_xpath(xpath)
        with auto.UIAutomationInitializerInThread():
            container = locate_lightning(steps, timeout=timeout)
            if container is None:
                return False

            matches = find_all_controls_by_text(container, button_text, timeout=2, control_type=None)
            if not matches:
                return False

            if index is not None:
                if index < 0 or index >= len(matches):
                    return False
                target = matches[index]
                if highlight: highlight_controls([target])
                elif click: click_control(target)
                return True

            if highlight: highlight_controls(matches)
            elif click: click_control(matches[0])
            return True
            
    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)
        return False
    
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("text", type=str)
    parser.add_argument("-c", "--click", action="store_true")
    parser.add_argument("-l", "--highlight", action="store_true")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--index", type=int, default=None)
    args = parser.parse_args()

    run(args.xpath, args.text, args.click, args.highlight, args.timeout, args.index)

if __name__ == "__main__":
    main()