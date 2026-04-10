import argparse
import sys
import os

# 确保可以导入项目根目录下的模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 导入 Hooks 模块
try:
    from hooks import get_text as get_text_hook
    from hooks import set_act as set_act_hook
    from probe import UIProbe
except ImportError as e:
    print(f"导入模块失败: {e}\n请确保在 win_ui_auto 目录下运行，且目录结构完整。")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Win UI Automation 统一调度工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # 1. 功能选择标志
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--find-el", action="store_true", help="探测模式 (F8 抓取信息)")
    group.add_argument("--get-text", action="store_true", help="获取文本 (调用 hooks/get_text.py)")
    group.add_argument("--set-act", action="store_true", help="执行动作 (调用 hooks/set_act.py)")

    # 2. 位置参数 (xpath, button_text)
    parser.add_argument("xpath", nargs="?", help="目标元素的 XPath")
    parser.add_argument("extra", nargs="?", help="额外参数: get-text下为depth, set-act下为button_text")

    # 3. 动作参数：-c 和 -l 现在可以接受可选的整数索引
    parser.add_argument("-c", "--click", nargs='?', const=True, default=None, type=int,
                        help="点击动作。不带参数时点击第一个匹配；带数字时点击第N个（从0开始）")
    parser.add_argument("-l", "--highlight", nargs='?', const=True, default=None, type=int,
                        help="高亮动作。不带参数时高亮所有匹配；带数字时只高亮第N个（从0开始）")
    parser.add_argument("--timeout", type=float, default=10.0, help="定位超时时间")

    # 处理无参数输入
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # 检查是否同时指定了 -c 和 -l
    if args.click is not None and args.highlight is not None:
        print("错误: -c 和 -l 不能同时使用", file=sys.stderr)
        sys.exit(1)

    # 对于 --set-act 模式，必须指定 -c 或 -l 之一
    if args.set_act and args.click is None and args.highlight is None:
        print("错误: --set-act 必须配合 -c (点击) 或 -l (高亮) 使用", file=sys.stderr)
        sys.exit(1)

    # --- 逻辑分发 ---

    if args.find_el:
        probe = UIProbe()
        probe.run()

    elif args.get_text:
        if not args.xpath:
            print("错误: --get-text 模式必须提供 xpath", file=sys.stderr)
            sys.exit(1)
        depth = int(args.extra) if args.extra and args.extra.isdigit() else 1
        get_text_hook.run(args.xpath, depth, args.timeout)

    elif args.set_act:
        if not args.xpath or not args.extra:
            print("错误: --set-act 模式必须提供 xpath 和 button_text", file=sys.stderr)
            sys.exit(1)

        # 解析 -c 和 -l 参数
        click = False
        highlight = False
        index = None

        if args.click is not None:
            click = True
            if args.click is not True:  # 如果提供了数字
                index = args.click
        elif args.highlight is not None:
            highlight = True
            if args.highlight is not True:
                index = args.highlight

        set_act_hook.run(
            xpath=args.xpath,
            button_text=args.extra,
            click=click,
            highlight=highlight,
            timeout=args.timeout,
            index=index
        )

if __name__ == "__main__":
    main()