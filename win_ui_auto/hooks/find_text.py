import argparse
import re
import time
import sys
import msvcrt
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
        # 每步的剩余超时时间 = 总超时时间 - 已用时间
        remaining = timeout - (time.time() - start_total)
        if remaining <= 0:
            print(f"定位失败：总超时时间已到", file=sys.stderr)
            return None
        
        # 显示倒计时提示（每秒更新）
        print(f"正在定位第 {idx+1}/{total_steps} 步: {ctrl_type} ...")
        while time.time() - step_start < remaining:
            elapsed = time.time() - step_start
            remain_step = max(0, remaining - elapsed)
            # 每0.5秒更新一次倒计时显示，避免刷新太快
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
                print()  # 换行
                break
            time.sleep(0.05)
        else:
            # 超时未找到
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

def find_button_in_container(container, button_text, timeout=1):
    """在容器内查找指定文字的按钮。返回按钮控件或 None。"""
    # 精确匹配 Name
    btn = container.ButtonControl(Name=button_text)
    end_time = time.time() + timeout
    while time.time() < end_time:
        if btn.Exists():
            return btn
        time.sleep(0.05)

    # 部分匹配：遍历直接子控件
    end_time = time.time() + timeout
    while time.time() < end_time:
        for child in container.GetChildren():
            if child.ControlTypeName == "ButtonControl" and child.Name and button_text in child.Name:
                return child
        time.sleep(0.05)

    # 递归搜索更深层（searchDepth 控制深度）
    btn = container.ButtonControl(searchDepth=3, Name=button_text)
    end_time = time.time() + timeout
    while time.time() < end_time:
        if btn.Exists():
            return btn
        time.sleep(0.05)

    return None

def highlight_button(btn):
    """高亮按钮，支持10秒倒计时自动退出"""
    rect = btn.BoundingRectangle
    if not rect or rect.width() <= 0 or rect.height() <= 0:
        print("按钮位置无效", file=sys.stderr)
        return False
    highlight = HighlightWindow()
    time.sleep(0.2)
    highlight.update(rect.left, rect.top, rect.width(), rect.height())
    print("已高亮按钮，按回车键立即退出，或等待10秒自动退出...")

    for i in range(10, 0, -1):
        print(f"\r倒计时 {i} 秒后自动退出...", end="", flush=True)
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b'\r', b'\n'):
                print("\n用户按回车退出")
                break
        time.sleep(1)
    else:
        print("\n超时自动退出")

    highlight.clear()
    highlight.stop()
    return True

def click_button(btn):
    """点击按钮"""
    try:
        btn.Click()
        print(f"已点击按钮: {btn.Name}")
        return True
    except Exception as e:
        print(f"点击失败: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description="在 XPath 指定的容器中查找按钮并执行操作")
    parser.add_argument("xpath", type=str, help="容器控件的 XPath")
    parser.add_argument("button_text", type=str, help="按钮上的文字")
    parser.add_argument("-c", "--click", action="store_true", help="点击按钮")
    parser.add_argument("-l", "--highlight", action="store_true", help="高亮按钮")
    parser.add_argument("--timeout", type=float, default=10, help="定位容器超时时间（秒），默认10秒")
    args = parser.parse_args()

    if not args.click and not args.highlight:
        print("错误：请指定 -c (点击) 或 -l (高亮)", file=sys.stderr)
        sys.exit(1)

    try:
        steps = parse_xpath(args.xpath)
    except Exception as e:
        print(f"XPath 解析错误: {e}", file=sys.stderr)
        sys.exit(1)

    container = locate_control_by_steps(steps, timeout=args.timeout)
    if container is None:
        print("无法定位容器", file=sys.stderr)
        sys.exit(1)

    btn = find_button_in_container(container, args.button_text, timeout=1)
    if btn is None:
        print(f"未找到文字为 '{args.button_text}' 的按钮", file=sys.stderr)
        sys.exit(1)

    if args.highlight:
        highlight_button(btn)
    elif args.click:
        click_button(btn)

if __name__ == "__main__":
    main()