import argparse
import sys
import os
import ctypes

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

# 全局变量，用于保存系统原始的无障碍状态
ORIGINAL_SCREEN_READER = False


def enable_os_accessibility():
    """【绝杀1】：向系统广播屏幕阅读器已启动，逼迫所有 CEF 放弃惰性渲染"""
    global ORIGINAL_SCREEN_READER
    try:
        user32 = ctypes.windll.user32
        SPI_GETSCREENREADER = 0x0046
        SPI_SETSCREENREADER = 0x0047

        current_state = ctypes.c_bool()
        user32.SystemParametersInfoW(SPI_GETSCREENREADER, 0, ctypes.byref(current_state), 0)
        ORIGINAL_SCREEN_READER = current_state.value

        # 开启全局标志 (2 = SPIF_SENDCHANGE, 触发全系统广播)
        user32.SystemParametersInfoW(SPI_SETSCREENREADER, 1, 0, 2)
        print("[系统护航] 已拉响 OS 级无障碍全局警报，目标应用渲染已强制激活！")
    except Exception as e:
        print(f"[系统护航] 开启 OS 警报失败: {e}")


def disable_os_accessibility():
    """恢复系统原始状态"""
    global ORIGINAL_SCREEN_READER
    try:
        SPI_SETSCREENREADER = 0x0047
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETSCREENREADER, int(ORIGINAL_SCREEN_READER), 0, 2
        )
        print("[系统护航] 已关闭 OS 级警报，系统无障碍状态已恢复。")
    except:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Win UI Automation 统一调度工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # 1. 功能选择标志
    group = parser.add_mutually_exclusive_group(required=True)
    # 【修改点 1】: --find-el 改为 --find
    group.add_argument("--find", action="store_true", help="探测模式 (F8 抓取信息)")
    group.add_argument("--get-text", action="store_true", help="获取文本 (调用 hooks/get_text.py)")
    group.add_argument("--set-act", action="store_true", help="执行动作 (调用 hooks/set_act.py)")

    # 2. 位置参数 (xpath, button_text/depth)
    parser.add_argument("xpath", nargs="?", help="目标元素的 XPath")
    parser.add_argument("extra", nargs="?", help="额外参数: get-text下为depth, set-act下为button_text")

    # 3. 动作参数
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

    if args.click is not None and args.highlight is not None:
        print("错误: -c 和 -l 不能同时使用", file=sys.stderr)
        sys.exit(1)

    if args.set_act and args.click is None and args.highlight is None:
        print("错误: --set-act 必须配合 -c (点击) 或 -l (高亮) 使用", file=sys.stderr)
        sys.exit(1)

    # =========================================================
    # 核心生命周期：在任何 UI 自动化操作前，开启系统级无障碍状态
    # =========================================================
    enable_os_accessibility()

    try:
        # --- 逻辑分发 ---
        # 【修改点 2】: args.find_el 改为 args.find
        if args.find:
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

            click = False
            highlight = False
            index = None

            if args.click is not None:
                click = True
                if args.click is not True:
                    index = args.click
            elif args.highlight is not None:
                highlight = True
                if args.highlight is not True:
                    index = args.highlight

            # 【终极修复】：纯位置传参，完全避免关键字参数名不匹配的报错
            # 参数顺序对应 set_act.py 中的 run(xpath, button_text, click, highlight, timeout, index)
            set_act_hook.run(
                args.xpath,
                args.extra,
                click,
                highlight,
                args.timeout,
                index
            )
    finally:
        # 无论程序正常退出还是报错崩溃，务必恢复系统状态！
        disable_os_accessibility()


if __name__ == "__main__":
    main()