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
from ctypes import wintypes
import datetime
from constants import DEBUG


def _configure_utf8_console():
    """
    让 Windows 控制台输出更稳定（避免默认 GBK 导致 UnicodeEncodeError/乱码）。
    - 优先 reconfigure stdout/stderr 为 UTF-8
    - 在 Windows 上尝试把 Console CodePage 切到 65001（失败则忽略）
    """
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
    except Exception:
        pass

try:
    from _version import __version__
except ImportError:
    __version__ = "dev"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 导入 Hooks 模块 (已移除 set_act_hook，引入 hl_hook 和 clk_hook)
try:
    from hooks import get as get_hook
    from hooks import el_if as el_if_hook
    from hooks import hl as hl_hook
    from hooks import clk as clk_hook
    from probe import UIProbe
except ImportError as e:
    print(f"导入模块失败: {e}\n请确保在 win_ui_auto 目录下运行，且目录结构完整。")
    sys.exit(1)

ORIGINAL_SCREEN_READER = False

def enable_os_accessibility():
    global ORIGINAL_SCREEN_READER
    try:
        user32 = ctypes.windll.user32
        SPI_GETSCREENREADER = 0x0046 
        SPI_SETSCREENREADER = 0x0047 

        current_state = ctypes.c_bool()
        user32.SystemParametersInfoW(SPI_GETSCREENREADER, 0, ctypes.byref(current_state), 0)
        ORIGINAL_SCREEN_READER = current_state.value

        result = user32.SystemParametersInfoW(SPI_SETSCREENREADER, 1, 0, 2)
        if result:
            write_main_log("[系统护航] 已拉响 OS 级无障碍全局警报，目标应用渲染已强制激活！")
        else:
            error_code = ctypes.windll.kernel32.GetLastError()
            write_main_log(f"[系统护航] 致命警告！护航 API 调用被系统拒绝。Windows 错误码: {error_code}")
    except Exception as e:
        write_main_log(f"[系统护航] 开启 OS 警报发生崩溃: {e}")

def force_wake_up_all_cef():
    try:
        user32 = ctypes.windll.user32 
        oleacc = ctypes.windll.oleacc 
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
        IID_IAccessible = GUID(0x618736e0, 0x3c3d, 0x11cf, (0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71)) 
        OBJID_CLIENT = -4 

        hwnds = []
        def enum_window_proc(hwnd, lParam):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if "Chrome_RenderWidgetHostHWND" in buf.value or "Render" in buf.value:
                if user32.IsWindowVisible(hwnd):
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    import psutil
                    try:
                        proc = psutil.Process(pid.value)
                        proc_name = proc.name().lower()
                        if "ideal.exe" in proc_name or "wxwork" in proc_name:
                            hwnds.append(hwnd)
                    except:
                        pass
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(0, EnumWindowsProc(enum_window_proc), 0)

        if hwnds:
            write_main_log(f"[系统护航] 发现 {len(hwnds)} 个底层 CEF 渲染节点，正在发送 COM 唤醒电信号...")
            for h in hwnds:
                pacc = ctypes.c_void_p()
                oleacc.AccessibleObjectFromWindow(h, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pacc))
            import time
            time.sleep(0.3)
            write_main_log("[系统护航] CEF 唤醒完毕，DOM 树已就绪。")
            
    except Exception as e:
        write_main_log(f"[系统护航] CEF 强制唤醒失败: {e}")

def disable_os_accessibility():
    global ORIGINAL_SCREEN_READER
    try:
        SPI_SETSCREENREADER = 0x0047
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETSCREENREADER, int(ORIGINAL_SCREEN_READER), 0, 2
        )
        write_main_log("[系统护航] 已关闭 OS 级警报，系统无障碍状态已恢复。") 
    except:
        pass

def main():
    _configure_utf8_console()
    parser = argparse.ArgumentParser(
        description="Win UI Automation 统一调度工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    if DEBUG:
        write_main_log(f"程序启动，接收到的原始参数: {sys.argv}")
        if not is_admin():
            write_main_log("[环境体检] 警告！当前运行权限: 普通用户 (Standard User)！极可能无法抓取高权限应用！")

    # 1. 功能选择标志 (把 hl 和 clk 提为核心互斥命令)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--find", action="store_true", help="探测模式 (F8 抓取信息)")
    group.add_argument("--get", action="store_true", help="获取目标元素的 UI 信息")
    group.add_argument("--if", action="store_true", help="判断元素是否存在 (返回 true/false)")
    group.add_argument("--hl", action="store_true", help="高亮目标元素")
    group.add_argument("--clk", action="store_true", help="点击目标元素")
    group.add_argument("--v", action="store_true", help="显示版本号")

    # 2. 位置参数
    parser.add_argument("xpath", nargs="?", help="目标元素的 XPath")

    # 3. 修饰参数 (新增 --type 和 --deep)
    parser.add_argument("--type", type=str, choices=["full", "text"], default="full", help="获取信息的类型")
    parser.add_argument("--deep", type=int, default=0, help="向下遍历的深度")
    parser.add_argument(
        "--match",
        "--master",
        dest="match",
        type=str,
        default=None,
        help="子元素文本模糊匹配 (支持 * 通配符)"
    )
    parser.add_argument("--index", type=int, default=None, help="匹配到的第几个元素 (从1开始)")     # <--- 新增
    parser.add_argument("--timeout", type=float, default=10.0, help="定位超时时间")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # =========================================================
    enable_os_accessibility()
    force_wake_up_all_cef()

    try:
        # --- 逻辑分发 ---
        if args.find:
            probe = UIProbe()
            probe.run()

        elif args.v:
            print("版本号: ", __version__)
            sys.exit(1)

        # --- 新增的获取信息分发 ---
        elif args.get:
            if not args.xpath:
                print("错误: --get 必须提供 xpath", file=sys.stderr)
                sys.exit(1)
            # 传入新增参数
            get_hook.run(
                xpath=args.xpath, 
                timeout=args.timeout, 
                get_type=args.type, 
                deep=args.deep
            )

        elif getattr(args, "if"):
            if not args.xpath:
                sys.exit(1)
            result = el_if_hook.run(args.xpath, args.timeout)

        elif args.hl:
            if not args.xpath:
                print("错误: --hl 必须提供 xpath", file=sys.stderr)
                sys.exit(1)
            hl_hook.run(
                xpath=args.xpath, 
                timeout=args.timeout, 
                match_pattern=args.match, 
                deep=args.deep, 
                index=args.index
            )

        elif args.clk:
            if not args.xpath:
                print("错误: --clk 必须提供 xpath", file=sys.stderr)
                sys.exit(1)
            clk_hook.run(
                xpath=args.xpath, 
                timeout=args.timeout, 
                match_pattern=args.match, 
                deep=args.deep, 
                index=args.index
            )

    finally:
        disable_os_accessibility()

if __name__ == "__main__":
    main()
