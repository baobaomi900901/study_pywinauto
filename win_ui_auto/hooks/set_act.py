# win_ui_auto/hooks/set_act.py
import sys
import os
import argparse
import re
import time
import fnmatch
import ctypes
from ctypes import wintypes
import uiautomation as auto
import datetime  # <--- 新增导入：用于写日志时间戳

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import DEBUG

try:
    import msvcrt
    from highlight import HighlightWindow
except ImportError:
    pass

def debug_print(msg):
    if DEBUG:
        print(msg, file=sys.stderr)
        # --- 新增：同步支持物理文件日志写入 ---
        try:
            base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            log_path = os.path.join(base_dir, "rpa_debug.log")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [set_act] {msg}\n")
        except:
            pass

def parse_xpath(xpath_str):
    if xpath_str.startswith('//'):
        xpath_str = xpath_str[2:]
    xpath_str = xpath_str.lstrip('/')
    steps = xpath_str.split('/')
    result = []
    for step in steps:
        if not step: continue
        match = re.match(r'^(\w+)(.*)$', step)
        if not match: continue
        ctrl_type = match.group(1)
        predicates = match.group(2).strip()
        attrs = {}
        position = None
        for block in re.findall(r'\[(.*?)\]', predicates):
            block = block.strip()
            if '=' in block:
                attr_match = re.match(r'@(\w+)=[\'"](.+?)[\'"]', block)
                if attr_match:
                    k, v = attr_match.groups()
                    attrs[k] = v
            else:
                try: position = int(block)
                except: pass
        result.append((ctrl_type, attrs, position))
    return result

def bridge_to_renderer(parent_hwnd):
    """绕过断层的 UIA 树，直接用底层 HWND 生成控件并唤醒（自带照妖镜）"""
    user32 = ctypes.windll.user32
    hwnds = []

    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if "Chrome_RenderWidgetHostHWND" in buf.value or "Render" in buf.value:
            # 照妖镜第一层：只抓可见的
            if user32.IsWindowVisible(h):
                hwnds.append(h)
        return True

    EnumChildProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(parent_hwnd, EnumChildProcType(enum_child_proc), 0)

    controls = []
    if not hwnds: return controls

    try:
        oleacc = ctypes.windll.oleacc
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
        IID_IAccessible = GUID(0x618736e0, 0x3c3d, 0x11cf, (0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71))
        OBJID_CLIENT = -4

        for h in hwnds:
            pacc = ctypes.c_void_p()
            oleacc.AccessibleObjectFromWindow(h, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pacc))
            try:
                ctrl = auto.ControlFromHandle(h)
                if ctrl:
                    # 照妖镜第二层：只抓有物理面积的
                    rect = ctrl.BoundingRectangle
                    if rect and rect.width() > 0 and rect.height() > 0:
                        controls.append(ctrl)
            except: pass
    except Exception as e:
        debug_print(f"桥接异常: {e}")
    return controls

def locate_control_by_steps(steps, timeout=10):
    current = auto.GetRootControl()
    start_total = time.time()
    idx = 0
    top_hwnd = 0

    while idx < len(steps):
        ctrl_type, attrs, position = steps[idx]
        remaining = timeout - (time.time() - start_total)
        if remaining <= 0:
            debug_print(f"定位失败：在第 {idx+1} 步超时")
            return None

        debug_print(f"正在定位第 {idx+1}/{len(steps)} 步: {ctrl_type} ...")
        
        if current and current.NativeWindowHandle:
            top_hwnd = current.NativeWindowHandle

        found = None
        end_time = time.time() + remaining
        search_depth = 4 if ctrl_type in ["Document", "Window", "Pane"] else 1

        # --- 给当前这一步加一个“只打印一次”的锁 ---
        has_printed_bridge = False 

        while time.time() < end_time:
            def search_descendants(node, max_d, current_d=1):
                results = []
                try: children = node.GetChildren()
                except: return results
                
                for child in children:
                    ctype = child.ControlTypeName.replace("Control", "")
                    is_match = (ctype == ctrl_type or ctrl_type == "*")
                    if not is_match and ctrl_type == "Document":
                        if "Render" in child.ClassName or child.ClassName == "Chrome_RenderWidgetHostHWND":
                            is_match = True
                            
                    if is_match:
                        ok = True
                        for k, v in attrs.items():
                            # ==========================================
                            # --- 核心外挂 1：自定义跨进程装甲 ProcessName ---
                            # ==========================================
                            if k == 'ProcessName':
                                try:
                                    import psutil
                                    pname = psutil.Process(child.ProcessId).name().lower()
                                    if v.lower() not in pname:
                                        ok = False
                                        break
                                except:
                                    ok = False
                                    break
                            # ==========================================
                            # 走传统的 UIA 属性比对
                            elif getattr(child, k, None) != v:
                                ok = False
                                break
                                
                        if ok: results.append(child)
                        
                    if current_d < max_d:
                        results.extend(search_descendants(child, max_d, current_d + 1))
                return results

            matched = search_descendants(current, search_depth)

            # HWND 桥接
            if not matched and ctrl_type == "Document":
                if not has_printed_bridge:
                    debug_print("UIA树断层，启动 HWND 底层强直连桥接...")
                    has_printed_bridge = True
                    
                bridge_controls = bridge_to_renderer(top_hwnd)
                if bridge_controls:
                    debug_print(f"HWND桥接成功！捕获并唤醒 {len(bridge_controls)} 个底层渲染节点")
                    matched.extend(bridge_controls)

            if matched:
                target_idx = (position - 1) if position and position <= len(matched) else 0
                if target_idx < len(matched):
                    found = matched[target_idx]
                    
                    # ====================================================
                    # --- 核心外挂 2：打破 Chromium 后台遮挡休眠机制 ---
                    # ====================================================
                    if ctrl_type in ["Pane", "Window"]:
                        try:
                            if hasattr(found, 'GetWindowPattern'):
                                found.GetWindowPattern().SetWindowVisualState(auto.WindowVisualState.Normal)
                            found.SetActive(waitTime=0.1)
                            time.sleep(0.3)
                            debug_print(f"[反休眠] 已将 {ctrl_type} 强行拽至前台，DOM 树已逼迫渲染就绪！")
                        except Exception as e:
                            pass
                    # ====================================================
                    
                    break
            
            # 智能跳级
            if not matched and ctrl_type == "Window":
                debug_print(f"第 {idx+1} 步 Window 未发现，智能跳过该层...")
                found = current
                break
                
            time.sleep(0.1)

        if not found:
            debug_print(f"定位断裂：第 {idx+1} 步未找到 {ctrl_type}")
            return None
        
        current = found
        idx += 1

    return current

def find_all_controls_by_text(container, text, timeout=2):
    use_wildcard = '*' in text or '?' in text
    matches = []

    def name_matches(name):
        if not name: return False
        if use_wildcard: return fnmatch.fnmatch(name.lower(), text.lower())
        return text in name

    debug_print(f"开始在容器内搜寻文字: '{text}' ...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        def walk(parent):
            try:
                for child in parent.GetChildren():
                    if name_matches(child.Name): matches.append(child)
                    walk(child)
            except: pass
        walk(container)
        if matches: break
        time.sleep(0.2)
        
    return matches

def highlight_controls(controls):
    if not controls: return False
    highlights = []
    for ctrl in controls:
        rect = ctrl.BoundingRectangle
        if rect and rect.width() > 0 and rect.height() > 0:
            hl = HighlightWindow()
            time.sleep(0.05)
            hl.update(rect.left, rect.top, rect.width(), rect.height())
            highlights.append(hl)
            
    timeout = 10
    start_time = time.time()
    debug_print(f"按回车键立即退出所有高亮，或等待 {timeout} 秒...")
    
    while time.time() - start_time < timeout:
        if msvcrt.kbhit() and msvcrt.getch() in (b'\r', b'\n'): break
        time.sleep(0.05)
    
    for hl in highlights:
        hl.clear()
        hl.stop()
    return True

def click_control(ctrl):
    debug_print(f"尝试点击控件: {ctrl.Name or 'Unnamed'} (类型: {ctrl.ControlTypeName})...")
    
    try:
        # ==========================================================
        # 1. 强力激活最上层窗口 (打破 Windows 后台焦点锁定机制)
        # ==========================================================
        try:
            top_win = ctrl.GetTopLevelControl()
            if top_win:
                hwnd = top_win.NativeWindowHandle
                if hwnd:
                    user32 = ctypes.windll.user32
                    
                    # 检查窗口是否最小化 (IsIconic)，如果是，则恢复它 (SW_RESTORE = 9)
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)
                        time.sleep(0.1)
                    
                    # 强制将窗口调到前台并赋予键盘焦点
                    user32.SetForegroundWindow(hwnd)
                
                # UIA 级别的双保险：确保视觉状态正常并尝试激活
                if hasattr(top_win, 'GetWindowPattern'):
                    try:
                        top_win.GetWindowPattern().SetWindowVisualState(auto.WindowVisualState.Normal)
                    except:
                        pass
                
                top_win.SetActive(waitTime=0.1)
                
                # 给 Windows 系统的窗口动画和前端 DOM 重绘留一点点时间
                time.sleep(0.2) 
        except Exception as e:
            debug_print(f" -> [警告] 尝试激活顶层窗口时出现异常: {e}")

        # 2. 物理校验：获取控件真实面积
        rect = ctrl.BoundingRectangle
        if not rect or rect.width() <= 0 or rect.height() <= 0:
            debug_print(" -> [失败] 控件没有有效物理面积，属于幽灵空壳")
            return False

        # 3. 强行将系统鼠标移动到控件中心！
        # 这一步极其关键：给前端网页 JS 一个 "Hover(鼠标悬停)" 的激活时间
        ctrl.MoveCursorToMyCenter()
        time.sleep(0.1) # 停顿 100 毫秒

        # 4. 执行纯物理点击！(彻底抛弃骗人的 InvokePattern)
        ctrl.Click(simulateMove=False)
        debug_print(" -> [成功] 已执行强制物理鼠标左击")
        return True

    except Exception as e:
        debug_print(f" -> [失败] 物理点击异常: {e}")
        return False

def run(xpath, button_text="", click=False, highlight=False, timeout=10, index=None):
    try:
        with auto.UIAutomationInitializerInThread():
            steps = parse_xpath(xpath)
            container = locate_control_by_steps(steps, timeout=timeout)
            
            if container is None:
                debug_print("[错误] 无法定位 XPath 对应的控件")
                print("false")
                return False

            # 场景 1: 没传 button_text，直接点容器本身
            if not button_text:
                if highlight: highlight_controls([container])
                if click: click_control(container)
                print("true")
                return True

            # 场景 2: 容器内寻找匹配文字 (如 "取消")
            matches = find_all_controls_by_text(container, button_text, timeout=2)
            if not matches:
                debug_print(f"[错误] 未找到匹配 '{button_text}' 的控件")
                print("false")
                return False

            if index is not None:
                if 0 <= index < len(matches):
                    target = matches[index]
                    if highlight: highlight_controls([target])
                    elif click: click_control(target)
                    print("true")
                    return True
                print("false")
                return False

            # 默认操作第一个匹配项
            if highlight: highlight_controls(matches)
            elif click: click_control(matches[0])
            print("true")
            return True
            
    except Exception as e:
        debug_print(f"执行异常: {e}")
        print("false")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("text", type=str, nargs="?", default="")
    parser.add_argument("--clk", action="store_true")
    parser.add_argument("--hl", action="store_true")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--index", type=int, default=None)
    args = parser.parse_args()
    run(args.xpath, args.text, args.clk, args.hl, args.timeout, args.index)

if __name__ == "__main__":
    main()

