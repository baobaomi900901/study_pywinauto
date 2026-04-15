# nuitka-project: --standalone
# nuitka-project: --onefile
# nuitka-project: --remove-output
# nuitka-project: --no-pyi-file
# nuitka-project: --output-dir=build
# nuitka-project: --output-filename=win_ui_auto
# nuitka-project: --file-version=0.0.0
# nuitka-project: --product-version=0.0.0
# nuitka-project: --product-name=win_ui_auto
# nuitka-project: --company-name=K-RPA Lite Team
# nuitka-project: --file-description=win_ui_auto
# nuitka-project: --include-package=uiautomation
# nuitka-project: --include-module=comtypes.stream
# nuitka-project: --include-module=csv
# nuitka-project: --include-module=email
# nuitka-project: --enable-plugin=tk-inter

import argparse
import sys
import os
import ctypes
from constants import DEBUG

__version__ = 10.0

def is_admin():
    """检查当前是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# ----------------- 新增全局日志函数 -----------------
def write_main_log(msg):
    if DEBUG:
        print(msg, file=sys.stderr)
        try:
            base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            log_path = os.path.join(base_dir, "rpa_debug.log")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [main] {msg}\n")
        except:
            pass

# 确保可以导入项目根目录下的模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 导入 Hooks 模块
try:
    from hooks import get_text as get_text_hook
    from hooks import set_act as set_act_hook
    from hooks import el_if as el_if_hook
    from probe import UIProbe
except ImportError as e:
    print(f"导入模块失败: {e}\n请确保在 win_ui_auto 目录下运行，且目录结构完整。")
    sys.exit(1)

# 全局变量，用于保存系统原始的无障碍状态
ORIGINAL_SCREEN_READER = False


def enable_os_accessibility():
    """【绝杀1】：向系统广播屏幕阅读器已启动"""
    global ORIGINAL_SCREEN_READER
    try:
        user32 = ctypes.windll.user32
        SPI_GETSCREENREADER = 0x0046
        SPI_SETSCREENREADER = 0x0047

        current_state = ctypes.c_bool()
        user32.SystemParametersInfoW(SPI_GETSCREENREADER, 0, ctypes.byref(current_state), 0)
        ORIGINAL_SCREEN_READER = current_state.value

        # 开启全局标志，并接收返回值
        result = user32.SystemParametersInfoW(SPI_SETSCREENREADER, 1, 0, 2)
        
        if result:
            write_main_log("[系统护航] 已拉响 OS 级无障碍全局警报，目标应用渲染已强制激活！")
        else:
            # 调用 GetLastError 获取 Windows 底层错误码
            error_code = ctypes.windll.kernel32.GetLastError()
            write_main_log(f"[系统护航] 致命警告！护航 API 调用被系统拒绝，可能没有生效。Windows 错误码: {error_code}")
            
    except Exception as e:
        write_main_log(f"[系统护航] 开启 OS 警报发生崩溃: {e}")


def disable_os_accessibility():
    """恢复系统原始状态"""
    global ORIGINAL_SCREEN_READER
    try:
        SPI_SETSCREENREADER = 0x0047
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETSCREENREADER, int(ORIGINAL_SCREEN_READER), 0, 2
        )
        
        write_main_log("[系统护航] 已关闭 OS 级警报，系统无障碍状态已恢复。") # 替换这行
    except:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Win UI Automation 统一调度工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    if DEBUG:
        write_main_log(f"程序启动，接收到的原始参数: {sys.argv}")
        args = sys.argv[1:]
        print('@main')
        print(args)

        # --- 新增：权限体检 ---
        if is_admin():
            write_main_log("[环境体检] 当前运行权限: 管理员 (Administrator) - 权限状态完美。")
        else:
            write_main_log("[环境体检] 警告！当前运行权限: 普通用户 (Standard User)！这极可能导致无法抓取高权限应用的 UI 元素！")

    # 1. 功能选择标志
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--find", action="store_true", help="探测模式 (F8 抓取信息)")
    group.add_argument("--get-text", action="store_true", help="获取文本 (调用 hooks/get_text.py)")
    group.add_argument("--set-act", action="store_true", help="执行动作 (调用 hooks/set_act.py)")
    group.add_argument("--if", action="store_true", help="判断元素是否存在 (返回 true/false)")
    group.add_argument("--v", action="store_true", help="显示版本号")

    # 2. 位置参数 (xpath, extra)
    parser.add_argument("xpath", nargs="?", help="目标元素的 XPath")
    parser.add_argument("extra", nargs="?", default="", help="额外参数: get-text下为depth, set-act下为[匹配文本]")

    # 3. 动作与修饰参数 (已修改为 --clk 和 --hl)
    parser.add_argument("--clk", action="store_true", help="点击动作")
    parser.add_argument("--hl", action="store_true", help="高亮动作")
    parser.add_argument("--index", type=int, default=None, help="高亮或点击第N个匹配项（从0开始）")
    parser.add_argument("--timeout", type=float, default=10.0, help="定位超时时间")

    # 处理无参数输入
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # 冲突校验
    if args.clk and args.hl:
        print("错误: --clk 和 --hl 不能同时使用", file=sys.stderr)
        sys.exit(1)

    if args.set_act and not args.clk and not args.hl:
        print("错误: --set-act 必须配合 --clk (点击) 或 --hl (高亮) 使用", file=sys.stderr)
        sys.exit(1)

    # =========================================================
    # 核心生命周期：在任何 UI 自动化操作前，开启系统级无障碍状态
    # =========================================================
    enable_os_accessibility()

    try:
        # --- 逻辑分发 ---
        if args.find:
            probe = UIProbe()
            probe.run()

        elif args.v:
            print("版本号: ", __version__)
            sys.exit(1)

        elif args.get_text:
            if not args.xpath:
                print("错误: --get-text 模式必须提供 xpath", file=sys.stderr)
                sys.exit(1)

            # 解析 depth 参数
            depth = 1
            if args.extra and args.extra.isdigit():
                depth = int(args.extra)

            get_text_hook.run(args.xpath, depth, args.timeout)

        elif args.set_act:
            if not args.xpath:
                print("错误: --set-act 模式必须提供 xpath", file=sys.stderr)
                sys.exit(1)

            set_act_hook.run(
                xpath=args.xpath,
                button_text=args.extra,
                click=args.clk,
                highlight=args.hl,
                timeout=args.timeout,
                index=args.index
            )
        elif getattr(args, "if"):   # 注意：--if 在 argparse 中存储为 args.if
            if not args.xpath:
                if DEBUG: print("错误: --if 需要提供 xpath", file=sys.stderr)
                sys.exit(1)
            result = el_if_hook.run(args.xpath, args.timeout)

    finally:
        # 无论程序正常退出还是报错崩溃，务必恢复系统状态！
        disable_os_accessibility()


if __name__ == "__main__":
    main()