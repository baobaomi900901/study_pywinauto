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


def locate_control_by_steps(steps, timeout=10):
    """
    最稳健的定位逻辑：逐层下钻
    兼容：将类名为 Chrome_RenderWidgetHostHWND 的 Pane 识别为 Document
    """
    current = auto.GetRootControl()
    start_total = time.time()

    for idx, (ctrl_type, attrs, position) in enumerate(steps):
        remaining = timeout - (time.time() - start_total)
        if remaining <= 0:
            return None

        found = None
        end_time = time.time() + remaining

        while time.time() < end_time:
            children = current.GetChildren()
            matched = []
            for child in children:
                ctype = child.ControlTypeName.replace("Control", "")

                # 核心兼容性匹配
                is_match = (ctype == ctrl_type or ctrl_type == "*")
                if not is_match and ctrl_type == "Document":
                    # 如果 XPath 找 Document，但实际是渲染器窗口容器
                    if "Render" in child.ClassName or child.ClassName == "Chrome_RenderWidgetHostHWND":
                        is_match = True

                if is_match:
                    ok = True
                    for k, v in attrs.items():
                        if getattr(child, k, None) != v:
                            ok = False
                            break
                    if ok:
                        matched.append(child)

            if matched:
                # 索引从 1 开始转换
                target_idx = (position - 1) if position and position <= len(matched) else 0
                found = matched[target_idx]
                break
            time.sleep(0.1)

        if not found:
            print(f"定位断裂：第 {idx+1} 步未找到 {ctrl_type}", file=sys.stderr)
            return None
        current = found

    return current


def find_all_controls_by_text(container, text, timeout=2):
    use_wildcard = '*' in text or '?' in text
    matches = []

    def name_matches(name):
        if not name:
            return False
        if use_wildcard:
            return fnmatch.fnmatch(name.lower(), text.lower())
        return text in name

    print(f"开始在容器内搜寻文字: '{text}' ...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        # 深度遍历容器下的所有子孙
        def walk(parent):
            for child in parent.GetChildren():
                if name_matches(child.Name):
                    matches.append(child)
                walk(child)

        walk(container)
        if matches:
            break
        time.sleep(0.2)

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

    timeout = 10
    start_time = time.time()
    last_sec = timeout
    print(f"按回车键立即退出所有高亮，或等待 {timeout} 秒自动退出...", end="", flush=True)

    while time.time() - start_time < timeout:
        remaining = int(timeout - (time.time() - start_time))
        if remaining != last_sec:
            print(f"\r按回车键立即退出所有高亮，或等待 {remaining} 秒自动退出...   ", end="", flush=True)
            last_sec = remaining
        if msvcrt.kbhit():
            if msvcrt.getch() in (b'\r', b'\n'):
                break
        time.sleep(0.05)

    print("\n[高亮结束]")
    for hl in highlights:
        hl.clear()
        hl.stop()
    return True


def click_control(ctrl):
    print(f"尝试点击控件: {ctrl.Name or 'Unnamed'} (类型: {ctrl.ControlTypeName})...")
    try:
        if hasattr(ctrl, 'GetInvokePattern'):
            ctrl.GetInvokePattern().Invoke()
            print(" -> [成功] InvokePattern 触发")
            return True
    except:
        pass
    try:
        ctrl.Click(simulateMove=False)
        print(" -> [成功] 物理点击触发")
        return True
    except Exception as e:
        print(f" -> [失败]: {e}")
        return False


def run(xpath, button_text="", click=False, highlight=False, timeout=10, index=None):
    try:
        steps = parse_xpath(xpath)
        # 使用初始化器确保线程安全
        with auto.UIAutomationInitializerInThread():
            container = locate_control_by_steps(steps, timeout=timeout)
            if container is None:
                print("[错误] 无法定位 XPath 对应的控件", file=sys.stderr)
                return False

            # 场景 1: 直接操作 XPath 目标
            if not button_text:
                if highlight:
                    return highlight_controls([container])
                if click:
                    return click_control(container)
                return True

            # 场景 2: 容器内搜索
            matches = find_all_controls_by_text(container, button_text, timeout=2)
            if not matches:
                print(f"[错误] 未找到匹配 '{button_text}' 的控件", file=sys.stderr)
                return False

            if index is not None:
                if 0 <= index < len(matches):
                    target = matches[index]
                    if highlight:
                        highlight_controls([target])
                    elif click:
                        click_control(target)
                    return True
                return False

            if highlight:
                highlight_controls(matches)
            elif click:
                click_control(matches[0])
            return True

    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)
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