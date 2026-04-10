# win_ui_auto/hooks/set_act.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import re
import time
import msvcrt
import fnmatch
import uiautomation as auto
from highlight import HighlightWindow

def parse_xpath(xpath_str):
    """解析简化 XPath，返回步骤列表。"""
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

def locate_control_by_steps(steps, timeout=2):
    """根据步骤列表定位控件，返回控件对象或 None。带有倒计时提示。"""
    root = auto.GetRootControl()
    current = root
    total_steps = len(steps)
    start_total = time.time()
    
    for idx, (ctrl_type, attrs, position) in enumerate(steps):
        step_start = time.time()
        found = None
        remaining = timeout - (time.time() - start_total)
        if remaining <= 0:
            print(f"定位失败：总超时时间已到", file=sys.stderr)
            return None
        
        print(f"正在定位第 {idx+1}/{total_steps} 步: {ctrl_type} ...")
        while time.time() - step_start < remaining:
            elapsed = time.time() - step_start
            remain_step = max(0, remaining - elapsed)
            if int(elapsed * 2) != int((elapsed - 0.05) * 2):
                print(f"\r  剩余 {remain_step:.1f} 秒", end="", flush=True)
            
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
                print()
                break
            time.sleep(0.05)
        else:
            print(f"\n定位失败：第 {idx+1} 步未找到控件 {ctrl_type} 属性 {attrs} 索引 {position}", file=sys.stderr)
            children = current.GetChildren()
            print("当前父控件的子控件列表：", file=sys.stderr)
            for i, child in enumerate(children[:30]):
                child_type = child.ControlTypeName
                cls = child.ClassName or ""
                name = (child.Name or "")[:50]
                print(f"  [{i}] {child_type} ClassName='{cls}' Name='{name}'", file=sys.stderr)
            return None
        current = found
    return current

def find_all_controls_by_text(container, text, timeout=2, control_type=None):
    """
    在容器内查找所有匹配指定文字（支持通配符 * 和 ?）的控件。
    返回控件列表（可能为空）。
    """
    use_wildcard = '*' in text or '?' in text
    matches = []

    def name_matches(name):
        if not name:
            return False
        if use_wildcard:
            return fnmatch.fnmatch(name.lower(), text.lower())
        else:
            return text in name

    # 1. 遍历直接子控件
    end_time = time.time() + timeout
    while time.time() < end_time:
        for child in container.GetChildren():
            if control_type is not None and child.ControlTypeName != control_type:
                continue
            if name_matches(child.Name):
                matches.append(child)
        if matches:
            break
        time.sleep(0.05)
    else:
        # 2. 递归搜索更深层（如果直接子控件没找到）
        def search_descendants(parent, depth):
            results = []
            if depth <= 0:
                return results
            for child in parent.GetChildren():
                if control_type is not None and child.ControlTypeName != control_type:
                    continue
                if name_matches(child.Name):
                    results.append(child)
                results.extend(search_descendants(child, depth-1))
            return results
        
        matches = search_descendants(container, 3)
    
    return matches

def highlight_controls(controls):
    """同时高亮多个控件，每个控件一个独立的高亮窗口。10秒后自动退出，或按回车键立即退出。"""
    if not controls:
        print("没有控件需要高亮", file=sys.stderr)
        return False
    
    # 为每个控件创建高亮窗口
    highlights = []
    valid_controls = []
    for ctrl in controls:
        rect = ctrl.BoundingRectangle
        if rect and rect.width() > 0 and rect.height() > 0:
            hl = HighlightWindow()
            # 稍微延迟确保窗口创建
            time.sleep(0.05)
            hl.update(rect.left, rect.top, rect.width(), rect.height())
            highlights.append(hl)
            valid_controls.append(ctrl)
        else:
            print(f"警告: 控件 '{ctrl.Name}' 位置无效，跳过高亮", file=sys.stderr)
    
    if not highlights:
        print("没有有效的高亮控件", file=sys.stderr)
        return False
    
    print(f"已高亮 {len(highlights)} 个控件:")
    for ctrl in valid_controls:
        print(f"  - {ctrl.Name} (类型: {ctrl.ControlTypeName})")
    print("按回车键立即退出所有高亮，或等待10秒自动退出...")
    
    # 等待10秒或按键
    start_time = time.time()
    while time.time() - start_time < 10:
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b'\r', b'\n'):
                print("\n用户按回车退出")
                break
        # 显示倒计时
        remaining = int(10 - (time.time() - start_time))
        if remaining > 0:
            print(f"\r倒计时 {remaining} 秒后自动退出...", end="", flush=True)
        time.sleep(0.2)
    else:
        print("\n超时自动退出")
    
    # 清除所有高亮窗口
    for hl in highlights:
        hl.clear()
        hl.stop()
    return True

def click_control(ctrl):
    """点击控件（仅第一个匹配）"""
    try:
        ctrl.Click()
        print(f"已点击控件: {ctrl.Name} (类型: {ctrl.ControlTypeName})")
        return True
    except Exception as e:
        print(f"点击失败: {e}", file=sys.stderr)
        return False

def run(xpath, button_text, click=False, highlight=False, timeout=10, index=None):
    try:
        steps = parse_xpath(xpath)
        container = locate_control_by_steps(steps, timeout=timeout)
        if container is None:
            print("无法定位容器", file=sys.stderr)
            # 调试输出...
            return False

        matches = find_all_controls_by_text(container, button_text, timeout=2, control_type=None)
        if not matches:
            print(f"未找到文字匹配 '{button_text}' 的控件", file=sys.stderr)
            # 调试输出...
            return False

        # 如果指定了索引
        if index is not None:
            if index < 0 or index >= len(matches):
                print(f"错误: 索引 {index} 超出范围，共有 {len(matches)} 个匹配控件", file=sys.stderr)
                return False
            target = matches[index]
            if highlight:
                highlight_controls([target])   # 只高亮这一个
            elif click:
                click_control(target)
            return True

        # 未指定索引，原行为
        if highlight:
            highlight_controls(matches)
        elif click:
            if len(matches) > 1:
                print(f"警告: 找到 {len(matches)} 个匹配控件，将只点击第一个。如需指定索引，请使用 --index 参数。", file=sys.stderr)
            click_control(matches[0])
        return True
    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)
        return False
    
def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("xpath", type=str, help="容器控件的 XPath")
    parser.add_argument("text", type=str, help="控件上的文字，支持通配符 * 和 ?")
    parser.add_argument("-c", "--click", action="store_true", help="点击控件")
    parser.add_argument("-l", "--highlight", action="store_true", help="高亮控件")
    parser.add_argument("--timeout", type=float, default=10, help="超时")
    parser.add_argument("--index", type=int, default=None, help="指定匹配列表中的索引（从0开始），仅操作该控件")
    args = parser.parse_args()

    if not args.click and not args.highlight:
        print("错误：请指定 -c 或 -l", file=sys.stderr)
        sys.exit(1)

    run(args.xpath, args.text, args.click, args.highlight, args.timeout, args.index)

if __name__ == "__main__":
    main()