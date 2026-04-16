# win_ui_auto/hooks/el_if.py
import sys
import os
import re
import time
import ctypes
from ctypes import wintypes
import uiautomation as auto
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import DEBUG


def debug_print(msg):
    if DEBUG:
        print(msg, file=sys.stderr)
        try:
            base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            log_path = os.path.join(base_dir, "rpa_debug.log")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [el_if] {msg}\n")
        except:
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
    """绕过断层的 UIA 树，直接用底层 HWND 生成控件并唤醒（自带照妖镜）"""
    user32 = ctypes.windll.user32
    hwnds = []

    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if "Chrome_RenderWidgetHostHWND" in buf.value or "Render" in buf.value:
            if user32.IsWindowVisible(h):
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
                    rect = ctrl.BoundingRectangle
                    if rect and rect.width() > 0 and rect.height() > 0:
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
        search_depth = 7 if ctrl_type in ["Document", "Window", "Pane", "Group", "Custom"] else 5

        has_printed_bridge = False

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
                            # 自定义跨进程装甲 ProcessName
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
                            else:
                                real_val = getattr(child, k, None)
                                if real_val is None:
                                    ok = False
                                    break
                                # 字符串属性：去除首尾空白后比较（兼容换行符、空格差异）
                                if isinstance(real_val, str) and isinstance(v, str):
                                    if real_val.strip() != v.strip():
                                        ok = False
                                        break
                                elif real_val != v:
                                    ok = False
                                    break

                        if ok:
                            results.append(child)

                    if current_d < max_d:
                        results.extend(search_descendants(child, max_d, current_d + 1))
                return results

            matched = search_descendants(current, search_depth)

            # 如果没找到且目标为 Document，尝试备用直接定位方法
            if not matched and ctrl_type == "Document":
                try:
                    name_filter = attrs.get('Name', '').strip()
                    if name_filter:
                        doc = current.DocumentControl(Name=name_filter)
                    else:
                        doc = current.DocumentControl()
                    if doc and doc.Exists(0):
                        matched = [doc]
                        debug_print("✅ 备用 DocumentControl 定位成功")
                except Exception as e:
                    debug_print(f"备用 DocumentControl 失败: {e}")

            # HWND 桥接（仅当控件疑似 CEF 窗口时才启用，避免误伤 Win32 原生应用）
            if not matched and ctrl_type == "Document":
                is_cef_window = False
                if current and hasattr(current, 'ClassName'):
                    class_name = current.ClassName or ""
                    if "Chrome_WidgetWin" in class_name or "Chrome_RenderWidgetHostHWND" in class_name:
                        is_cef_window = True

                if is_cef_window:
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

                    # 打破 Chromium 后台遮挡休眠机制
                    if ctrl_type == "Window" or (ctrl_type == "Pane" and idx == 0):
                        try:
                            if hasattr(found, 'GetWindowPattern'):
                                found.GetWindowPattern().SetWindowVisualState(auto.WindowVisualState.Normal)
                            found.SetActive(waitTime=0.1)
                            time.sleep(0.3)
                            debug_print(f"[反休眠] 已将顶级 {ctrl_type} 强行拽至前台，DOM 树已逼迫渲染就绪！")
                        except Exception as e:
                            pass

                    break

            # 如果 Window 层没找到，允许智能跳过（但这种情况极少发生）
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
                # 内容探活：向下探2层检查是否有文本
                texts = collect_child_texts(control, max_depth=2)

                if len(texts) > 0:
                    print("true")
                    return True
                else:
                    debug_print("判定假死：控件容器存在，但内部完全没有任何文本，是一个空壳")
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