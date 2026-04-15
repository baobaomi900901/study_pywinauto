# win_ui_auto/hooks/get_text.py
import sys
import os
import argparse
import re
import time
import json
import ctypes
from ctypes import wintypes
import uiautomation as auto
from constants import DEBUG

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def debug_print(msg):
    if DEBUG:
        # 1. 继续输出到 stderr
        print(msg, file=sys.stderr)
        
        # 2. 写入到物理文件 rpa_debug.log 中
        try:
            # 获取当前运行的 exe 或 py 所在的目录
            base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            log_path = os.path.join(base_dir, "rpa_debug.log")
            
            # 生成带时间戳的日志
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            log_line = f"[{timestamp}] [get_text] {msg}\n"
            
            # 使用 a 模式追加写入
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception:
            pass


def parse_xpath(xpath_str):
    if xpath_str.startswith('//'):
        xpath_str = xpath_str[2:]
    xpath_str = xpath_str.lstrip('/')
    steps = xpath_str.split('/')
    result = []
    for step in steps:
        if not step:
            continue
        match = re.match(r'^(\w+)(.*)$', step)
        if not match:
            continue
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
                try:
                    position = int(block)
                except:
                    pass
        result.append((ctrl_type, attrs, position))
    return result


def bridge_to_renderer(parent_hwnd):
    """桥接断层，直取底层渲染句柄"""
    user32 = ctypes.windll.user32
    hwnds = []

    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if "Chrome_RenderWidgetHostHWND" in buf.value or "Render" in buf.value:
            hwnds.append(h)
        return True

    EnumChildProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(parent_hwnd, EnumChildProcType(enum_child_proc), 0)

    controls = []
    if not hwnds:
        return controls

    try:
        oleacc = ctypes.windll.oleacc

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong),
                        ("Data2", ctypes.c_ushort),
                        ("Data3", ctypes.c_ushort),
                        ("Data4", ctypes.c_ubyte * 8)]

        IID_IAccessible = GUID(0x618736e0, 0x3c3d, 0x11cf,
                               (0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71))
        OBJID_CLIENT = -4

        for h in hwnds:
            pacc = ctypes.c_void_p()
            oleacc.AccessibleObjectFromWindow(h, OBJID_CLIENT,
                                               ctypes.byref(IID_IAccessible),
                                               ctypes.byref(pacc))
            try:
                ctrl = auto.ControlFromHandle(h)
                if ctrl:
                    controls.append(ctrl)
            except:
                pass
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

        # --- 核心修复：只在跳跃外层架构时使用深搜，一旦进入内部(Group等)，严格只找一层！ ---
        search_depth = 4 if ctrl_type in ["Document", "Window", "Pane"] else 1

        while time.time() < end_time:
            def search_descendants(node, max_d, current_d=1):
                results = []
                try:
                    children = node.GetChildren()
                except:
                    return results

                for child in children:
                    ctype = child.ControlTypeName.replace("Control", "")
                    is_match = (ctype == ctrl_type or ctrl_type == "*")
                    if not is_match and ctrl_type == "Document":
                        if "Render" in child.ClassName or child.ClassName == "Chrome_RenderWidgetHostHWND":
                            is_match = True

                    if is_match:
                        ok = True
                        for k, v in attrs.items():
                            if getattr(child, k, None) != v:
                                ok = False
                                break
                        if ok:
                            results.append(child)

                    if current_d < max_d:
                        results.extend(search_descendants(child, max_d, current_d + 1))
                return results

            matched = search_descendants(current, search_depth)

            # HWND 桥接
            if not matched and ctrl_type == "Document":
                debug_print("UIA树断层，启动 HWND 底层强直连桥接...")
                bridge_controls = bridge_to_renderer(top_hwnd)
                if bridge_controls:
                    debug_print(f"HWND桥接成功！捕获并唤醒 {len(bridge_controls)} 个底层渲染节点")
                    matched.extend(bridge_controls)

            if matched:
                target_idx = (position - 1) if position and position <= len(matched) else 0
                if target_idx < len(matched):
                    found = matched[target_idx]
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


def collect_child_texts(control, max_depth=1, current_depth=0):
    texts = []
    content = ""
    try:
        if hasattr(control, 'GetValuePattern'):
            content = control.GetValuePattern().Value
    except:
        pass

    if not content and control.Name:
        content = control.Name

    if content and content.strip():
        texts.append(content.strip())

    if current_depth < max_depth:
        for child in control.GetChildren():
            texts.extend(collect_child_texts(child, max_depth, current_depth + 1))

    res, seen = [], set()
    for t in texts:
        if t not in seen:
            res.append(t)
            seen.add(t)
    return res


def run(xpath, depth=1, timeout=10):
    if DEBUG:
        args = sys.argv[1:]
        print('@get-text')
        print(args)

    try:
        with auto.UIAutomationInitializerInThread():
            steps = parse_xpath(xpath)
            control = locate_control_by_steps(steps, timeout=timeout)
            if control is None:
                print("[]")
                return []

            texts = collect_child_texts(control, max_depth=depth)
            print(json.dumps(texts, ensure_ascii=False))
            return texts
    except Exception as e:
        debug_print(f"执行异常: {e}")
        print("[]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("depth", type=int, nargs='?', default=1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    run(args.xpath, args.depth, args.timeout)


if __name__ == "__main__":
    main()