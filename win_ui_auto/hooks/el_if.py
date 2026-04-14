# win_ui_auto/hooks/el_if.py
import sys
import os
import re
import time
import ctypes
from ctypes import wintypes
import uiautomation as auto

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import DEBUG


def debug_print(msg):
    if DEBUG:
        print(msg, file=sys.stderr)


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
    """绕过断层的 UIA 树，直接用底层 HWND 生成控件并唤醒"""
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
            except Exception:
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
                        if ("Render" in child.ClassName or
                                child.ClassName == "Chrome_RenderWidgetHostHWND"):
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
                        results.extend(search_descendants(child, max_d,
                                                           current_d + 1))
                return results

            matched = search_descendants(current, search_depth)

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
    """递归收集文本，用于验证控件是否为空壳"""
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

    return [t for t in texts if t]


def run(xpath, timeout=10.0):
    """判断控件是否存在且有实质内容，只向 stdout 打印 true 或 false"""
    try:
        with auto.UIAutomationInitializerInThread():
            steps = parse_xpath(xpath)
            control = locate_control_by_steps(steps, timeout=timeout)

            if control is not None:
                # --- 【核心逻辑：内容探活】 ---
                # 哪怕这个控件在内存里，哪怕它有长宽，我们也要榨一榨它里面有没有水
                # 稍微向下探 2 层，防止文本包在子 Group 里
                texts = collect_child_texts(control, max_depth=2)

                if len(texts) > 0:
                    print("true")
                    return True
                else:
                    debug_print(f"判定假死：控件容器存在，但内部完全没有任何文本，是一个空壳")
                    print("false")
                    return False
            else:
                print("false")
                return False
    except Exception as e:
        debug_print(f"执行异常: {e}")
        print("false")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    run(args.xpath, args.timeout)


if __name__ == "__main__":
    main()