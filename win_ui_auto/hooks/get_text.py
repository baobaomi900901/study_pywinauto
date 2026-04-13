# win_ui_auto/hooks/get_text.py
import sys
import os
import argparse
import re
import time
import json
import uiautomation as auto

# 确保可以导入项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    改进版逐层定位：
    兼容处理 Chromium 架构中 Document 层可能被识别为 Pane 的情况。
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
                # 获取缩写类型
                ctype = child.ControlTypeName.replace("Control", "")

                # --- 核心兼容逻辑 ---
                is_match = (ctype == ctrl_type or ctrl_type == "*")

                # 如果 XPath 找 Document，但实际 UIA 树节点是 Pane (Chrome 渲染器的常见变体)
                if not is_match and ctrl_type == "Document":
                    if child.ClassName == "Chrome_RenderWidgetHostHWND" or "Render" in child.ClassName:
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
                target_idx = (position - 1) if position and position <= len(matched) else 0
                found = matched[target_idx]
                break
            time.sleep(0.1)

        if not found:
            print(f"定位断裂：第 {idx+1} 步未找到 {ctrl_type}", file=sys.stderr)
            return None
        current = found

    return current


def collect_child_texts(control, max_depth=1, current_depth=0):
    """递归收集文本，增加对 Value 属性的提取"""
    texts = []

    # 提取当前内容：优先 Value，其次 Name
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

    # 去重
    res, seen = [], set()
    for t in texts:
        if t not in seen:
            res.append(t)
            seen.add(t)
    return res


def run(xpath, depth=1, timeout=10):
    try:
        # 使用初始化器确保 COM 线程安全
        with auto.UIAutomationInitializerInThread():
            steps = parse_xpath(xpath)
            control = locate_control_by_steps(steps, timeout=timeout)
            if control is None:
                return None

            texts = collect_child_texts(control, max_depth=depth)
            print(json.dumps(texts, ensure_ascii=False))
            return texts
    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("depth", type=int, nargs='?', default=1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    run(args.xpath, args.depth, args.timeout)


if __name__ == "__main__":
    main()