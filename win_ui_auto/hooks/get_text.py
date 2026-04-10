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

# 确保可以导入父目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def force_wake_up_chromium(hwnd):
    """底层 COM 强索：逼迫休眠的 Chromium 瞬间序列化 DOM 树"""
    try:
        oleacc = ctypes.windll.oleacc

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

        IID_IAccessible = GUID(0x618736e0, 0x3c3d, 0x11cf, (0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71))
        OBJID_CLIENT = -4
        pacc = ctypes.c_void_p()
        oleacc.AccessibleObjectFromWindow(hwnd, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pacc))
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
            raise ValueError(f"无法解析: {step}")
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
                try:
                    position = int(block)
                except:
                    pass
        result.append((control_type, attrs, position))
    return result


def locate_lightning(steps, timeout=10):
    """【大招：闪电穿透算法】毫秒级重试整条链路，树一旦建好瞬间直达谷底"""
    render_hwnds = get_all_render_hwnds()
    if not render_hwnds:
        print("[闪电战] 未找到 Chromium 渲染底板，请确认界面已开启。", file=sys.stderr)
        return None

    # 剔除不稳定的外壳层，只保留 Document 以后的真实 DOM 节点
    doc_index = -1
    for i, step in enumerate(steps):
        if step[0] == "Document":
            doc_index = i
            break

    if doc_index == -1:
        print("[闪电战] XPath 中未包含 Document 层。", file=sys.stderr)
        return None

    virtual_steps = steps[doc_index + 1:]

    print(f"[闪电战] 锁定 {len(render_hwnds)} 个渲染器。准备下潜 {len(virtual_steps)} 层...", file=sys.stderr)

    start_time = time.time()
    attempts = 0

    while time.time() - start_time < timeout:
        attempts += 1

        for hwnd in render_hwnds:
            force_wake_up_chromium(hwnd)

            try:
                # 建立在渲染器上的 UIA 根节点
                current = auto.ControlFromHandle(hwnd)
                success = True

                # 开始极限速降
                for ctrl_type, attrs, position in virtual_steps:
                    # 使用原生 GetChildren 进行纯内存过滤，速度远超 Auto.Control() 搜寻
                    children = current.GetChildren()
                    matched = []

                    for child in children:
                        ctype = child.ControlTypeName
                        if ctype.endswith("Control"):
                            ctype = ctype[:-7]
                        if ctype != ctrl_type and ctrl_type != "*":
                            continue

                        ok = True
                        for k, v in attrs.items():
                            if k == 'ClassName' and child.ClassName != v:
                                ok = False
                                break
                            if k == 'Name' and child.Name != v:
                                ok = False
                                break
                            if k == 'AutomationId' and child.AutomationId != v:
                                ok = False
                                break
                        if ok:
                            matched.append(child)

                    target_idx = (position - 1) if position else 0
                    if target_idx < len(matched):
                        current = matched[target_idx]
                    else:
                        # 核心：只要有任意一层断裂，直接放弃当前 HWND 的本次尝试！
                        success = False
                        break

                if success:
                    cost_time = time.time() - start_time
                    print(f"\n[闪电战] 击穿成功！总耗时: {cost_time:.2f}秒 (冲锋次数: {attempts})", file=sys.stderr)
                    return current

            except Exception:
                pass

        # 所有 HWND 在本轮都断裂了，说明 Chromium 还在渲染，稍微喘息 0.1 秒后发起下一轮总攻
        time.sleep(0.1)

    print("\n[闪电战] 超时：渲染树未能在此时间内生成。", file=sys.stderr)
    return None


def collect_child_texts(control, max_depth=1, current_depth=0):
    texts = []
    if current_depth == 0 and control.Name:
        texts.append(control.Name)
    if current_depth < max_depth:
        for child in control.GetChildren():
            if child.Name:
                texts.append(child.Name)
            texts.extend(collect_child_texts(child, max_depth, current_depth + 1))
    return texts


def run(xpath, depth=1, timeout=10):
    try:
        steps = parse_xpath(xpath)
        with auto.UIAutomationInitializerInThread():
            control = locate_lightning(steps, timeout=timeout)
            if control is None:
                print("无法定位控件", file=sys.stderr)
                return None

            texts = collect_child_texts(control, max_depth=depth)
            print("\n[抓取结果]:")
            print(json.dumps(texts, ensure_ascii=False))
            return texts
    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("depth", type=int, nargs='?', default=1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    if args.depth < 0:
        sys.exit(1)
    run(args.xpath, args.depth, args.timeout)


if __name__ == "__main__":
    main()