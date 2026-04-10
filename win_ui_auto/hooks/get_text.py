# win_ui_auto/hooks/get_text.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import re
import time
import json
import uiautomation as auto

def parse_xpath(xpath_str):
    """解析简化 XPath，返回步骤列表。支持 // 开头的任意深度（简化为从根开始）。"""
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
            raise ValueError(f"无法解析步骤: {step}")
        control_type = match.group(1)
        predicates = match.group(2).strip()
        attrs = {}
        position = None
        for block in re.findall(r'\[(.*?)\]', predicates):
            block = block.strip()
            if '=' in block:
                attr_match = re.match(r'@(\w+)=\'(.+)\'', block)
                if not attr_match:
                    attr_match = re.match(r'@(\w+)="(.+)"', block)
                if attr_match:
                    attr_name, attr_value = attr_match.groups()
                    attrs[attr_name] = attr_value
                else:
                    raise ValueError(f"无法解析属性条件: {block}")
            else:
                try:
                    position = int(block)
                except ValueError:
                    raise ValueError(f"无效的位置索引: {block}")
        result.append((control_type, attrs, position))
    return result

def locate_control_by_steps(steps, timeout=10):
    """根据步骤列表定位控件，返回控件对象或 None。"""
    root = auto.GetRootControl()
    current = root
    total_steps = len(steps)
    start_total = time.time()
    
    for idx, (ctrl_type, attrs, position) in enumerate(steps):
        remaining = timeout - (time.time() - start_total)
        if remaining <= 0:
            print(f"定位失败：总超时时间已到", file=sys.stderr)
            return None
        
        print(f"正在定位第 {idx+1}/{total_steps} 步: {ctrl_type} ...", file=sys.stderr)
        found = None
        end_time = time.time() + remaining
        while time.time() < end_time:
            children = current.GetChildren()
            matched = []
            for child in children:
                child_type_short = child.ControlTypeName
                if child_type_short.endswith("Control"):
                    child_type_short = child_type_short[:-7]
                if child_type_short != ctrl_type:
                    continue
                ok = True
                for attr_name, attr_value in attrs.items():
                    if attr_name == "ClassName":
                        if child.ClassName != attr_value:
                            ok = False
                            break
                    elif attr_name == "Name":
                        if child.Name != attr_value:
                            ok = False
                            break
                    elif attr_name == "AutomationId":
                        if child.AutomationId != attr_value:
                            ok = False
                            break
                if ok:
                    matched.append(child)
            if matched:
                if position is not None and 1 <= position <= len(matched):
                    found = matched[position - 1]
                else:
                    found = matched[0]
                break
            time.sleep(0.05)
        
        if found is None:
            print(f"\n定位失败：第 {idx+1} 步未找到控件 {ctrl_type}", file=sys.stderr)
            return None
        current = found
    return current

def collect_child_texts(control, max_depth=1, current_depth=0):
    """
    递归收集控件及其子控件的 Name 属性（非空）。
    max_depth: 最大递归深度，0 表示只收集当前控件自身，1 表示当前控件+直接子控件，以此类推。
    返回字符串列表。
    """
    texts = []
    # 收集当前控件的 Name（如果非空）
    if current_depth == 0 and control.Name:
        texts.append(control.Name)
    # 如果还没达到最大深度，继续遍历子控件
    if current_depth < max_depth:
        for child in control.GetChildren():
            if child.Name:
                texts.append(child.Name)
            # 递归更深层（深度+1）
            texts.extend(collect_child_texts(child, max_depth, current_depth + 1))
    return texts

def run(xpath, depth=1, timeout=10):
    """供外部调用的入口函数"""
    try:
        steps = parse_xpath(xpath)
        control = locate_control_by_steps(steps, timeout=timeout)
        if control is None:
            print("无法定位控件", file=sys.stderr)
            return None

        texts = collect_child_texts(control, max_depth=depth)
        # 保持你原始的输出格式
        print(json.dumps(texts, ensure_ascii=False))
        return texts
    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="通过简化 XPath 定位控件，并返回其子控件的文本列表")
    parser.add_argument("xpath", type=str, help="控件的简化 XPath")
    parser.add_argument("depth", type=int, nargs='?', default=1, help="深度")
    parser.add_argument("--timeout", type=float, default=10, help="超时")
    args = parser.parse_args()

    if args.depth < 0:
        print("错误：depth 必须 >= 0", file=sys.stderr)
        sys.exit(1)
        
    # 调用封装好的 run
    run(args.xpath, args.depth, args.timeout)

if __name__ == "__main__":
    main()