# win_ui_auto/hooks/el_if.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import re
import time
import uiautomation as auto
from constants import DEBUG

def parse_xpath(xpath_str):
    """将 XPath 解析为步骤列表，与 set_act.py 中的实现一致"""
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
    """逐层定位控件，超时返回 None"""
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
                is_match = (ctype == ctrl_type or ctrl_type == "*")
                # 兼容 Chrome / Electron 渲染器
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
                        matched.append(child)
            if matched:
                target_idx = (position - 1) if position and position <= len(matched) else 0
                found = matched[target_idx]
                break
            time.sleep(0.1)

        if not found:
            if DEBUG:
                print(f"定位断裂：第 {idx+1} 步未找到 {ctrl_type}", file=sys.stderr)
            return None
        current = found
    return current

def run(xpath, timeout=10.0):
    """判断控件是否存在，返回 bool"""
    try:
        steps = parse_xpath(xpath)
        with auto.UIAutomationInitializerInThread():
            control = locate_control_by_steps(steps, timeout=timeout)
            exists = control is not None
            if DEBUG:
                print(f"[el_if] 控件{'存在' if exists else '不存在'}: {xpath}")
            return exists
    except Exception as e:
        if DEBUG:
            print(f"[el_if] 执行异常: {e}", file=sys.stderr)
        return False

def main():
    """命令行测试入口"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = run(args.xpath, args.timeout)
    print(str(result).lower())

if __name__ == "__main__":
    main()