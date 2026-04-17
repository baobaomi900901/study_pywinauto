# ./win_ui_auto/probe.py
import threading
import time
import ctypes
import re # 新增正则库用于优化 XPath
from ctypes import wintypes
from constants import *
from highlight import HighlightWindow
from listeners import KeyboardListener, MouseMoveListener
from capture_overlay import CaptureOverlay
from control_info import get_deepest_control, get_control_info, print_control_info, write_control_info_to_file


class UIProbe:
    def __init__(self):
        self.running = True
        self.inspect_mode = False
        self.current_control = None
        self.control_lock = threading.Lock()
        self.latest_coord = None
        self.coord_lock = threading.Lock()
        self.last_processed_coord = None
        self.last_printed_id = None
        self.last_print_time = 0
        self.print_interval = 0.1
        self.last_mouse_move_ts = time.monotonic()

        self.highlight = HighlightWindow()
        self.keyboard = KeyboardListener()
        self.mouse_move = MouseMoveListener(on_move=self._on_mouse_move)
        # 使用全屏透明遮罩：探测模式下所有点击先落到遮罩层，目标应用收不到点击
        self.overlay = CaptureOverlay(
            is_enabled=lambda: self.inspect_mode,
            on_capture=self._on_f8,
            debug_print=write_main_log if DEBUG else None,
        )

    def _exit_inspect_mode(self, reason: str):
        if not self.inspect_mode:
            return
        self.inspect_mode = False
        try:
            self.overlay.hide()
        except Exception:
            pass
        self.highlight.clear()
        with self.control_lock:
            self.current_control = None
        print(f"\n[探查模式] 已自动关闭（{reason}）")

    def _wake_up_com_interface(self, x, y):
        """【绝杀2】：强取 COM 接口，精准穿透透明防弹玻璃"""
        user32 = ctypes.windll.user32

        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND

        pt = wintypes.POINT(x, y)
        hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return

        root_hwnd = user32.GetAncestor(hwnd, 2)
        if not root_hwnd:
            root_hwnd = hwnd

        target_hwnds = [hwnd, root_hwnd]

        def enum_child_proc(h, lParam):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, buf, 256)
            if buf.value == "Chrome_RenderWidgetHostHWND":
                target_hwnds.append(h)
            return True

        EnumChildProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(root_hwnd, EnumChildProcType(enum_child_proc), 0)

        try:
            oleacc = ctypes.windll.oleacc

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", ctypes.c_ulong),
                            ("Data2", ctypes.c_ushort),
                            ("Data3", ctypes.c_ushort),
                            ("Data4", ctypes.c_ubyte * 8)]

            IID_IAccessible = GUID(0x618736e0, 0x3c3d, 0x11cf,
                                  (0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71))
            OBJID_CLIENT = -4

            for t_hwnd in set(target_hwnds):
                pacc = ctypes.c_void_p()
                # 强行索要 IAccessible 对象！
                oleacc.AccessibleObjectFromWindow(t_hwnd, OBJID_CLIENT,
                                                  ctypes.byref(IID_IAccessible),
                                                  ctypes.byref(pacc))
        except:
            pass

    def _optimize_cef_xpath(self, raw_xpath, process_name=""):
        """【终极净水器】强力清洗 CEF 架构的 XPath，并自动打上进程基因锁"""
        xpath = raw_xpath
        if "Chrome_WidgetWin_1" in xpath:
            # 1. 斩断外围乱象：移除 Pane 后面的所有变动索引
            xpath = re.sub(r"(Pane\[@ClassName='Chrome_WidgetWin_1'\])\[\d+\]", r"\1", xpath)
            
            # ====================================================
            # --- 新增：自动把进程名作为基因锁，焊死在第一层大门上 ---
            if process_name:
                xpath = xpath.replace(
                    "Pane[@ClassName='Chrome_WidgetWin_1']", 
                    f"Pane[@ClassName='Chrome_WidgetWin_1'][@ProcessName='{process_name}']"
                )
            # ====================================================

            # 2. 移除极其不稳定的 Window 层级
            xpath = re.sub(r"/Window(?:\[.*?\])?(?:\[\d+\])?", "", xpath)
            
            # 3. 核弹级清洗 Document
            xpath = re.sub(r"/Document(?:\[.*?\])*", "/Document", xpath)
            
            # 4. 重新穿上标准化、带穿透属性的护甲
            xpath = xpath.replace("/Document", "//Document[@ClassName='Chrome_RenderWidgetHostHWND']")
            
            # 5. 清理多余的斜杠
            xpath = xpath.replace("///", "//")
            
        return xpath

    def _on_f8(self):
        if not self.inspect_mode:
            return
        print("\n[F8] 已按下，获取当前控件信息...")
        with self.control_lock:
            control = self.current_control

        if control:
            rect = control.BoundingRectangle
            if rect:
                x = rect.left + rect.width() // 2
                y = rect.top + rect.height() // 2
                info = get_control_info(control, x, y, self.highlight.get_pid())

                if info:
                    # ==========================================
                    # 在打印和写入文件之前，执行 XPath 净化！
                    if 'xpath' in info:
                        # info['raw_xpath'] = info['xpath']  # 留档原始路径供参考
                        
                        # # --- 新增：获取当前目标控件的系统进程名 ---
                        # pname = ""
                        # try:
                        #     import psutil
                        #     # control.ProcessId 是 UIA 原生提供的属性
                        #     pname = psutil.Process(control.ProcessId).name().lower()
                        # except Exception:
                        #     pass
                            
                        # # 把获取到的进程名传给净水器！
                        # info['xpath'] = self._optimize_cef_xpath(info['xpath'], process_name=pname)
                    
                        info['raw_xpath'] = info['xpath']
                        pname = ""
                        try:
                            import psutil
                            pname = psutil.Process(control.ProcessId).name().lower()
                        except Exception:
                            pass
                        
                        info['xpath'] = self._optimize_cef_xpath(info['xpath'], process_name=pname)
                        
                        # --- 新增：无痕自动写入系统剪贴板 ---
                        try:
                            import tkinter as tk
                            r = tk.Tk()
                            r.withdraw()
                            r.clipboard_clear()
                            r.clipboard_append(f'"{info["xpath"]}"')
                            r.update()
                            r.destroy()
                            print("\n[辅助] XPath 已自动复制到系统剪贴板，直接 Ctrl+V 即可使用。")
                        except Exception as e:
                            pass
                    # ==========================================

                    self.last_printed_id, self.last_print_time = print_control_info(
                        info, self.last_printed_id, self.last_print_time, self.print_interval
                    )
                    write_control_info_to_file(info)
                    # print("→ 信息已写入 el.json")
                    # print("→ 信息已打印")

                    # 打印成功后自动退出探测模式，避免误触连续抓取
                    self._exit_inspect_mode("已抓取信息；如需继续请输入 1 重新开启")
                else:
                    print("→ 获取控件信息失败")
            else:
                print("→ 控件无边界矩形")
        else:
            print("→ 当前没有悬停控件，请先移动鼠标至目标控件并等待高亮")

    def _on_mouse_move(self, x, y):
        self.last_mouse_move_ts = time.monotonic()
        with self.coord_lock:
            self.latest_coord = (x, y)

    def _uia_worker(self):
        print("[UI探测] 线程启动...")
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():
                print("[UI探测] COM初始化成功")
                pending_coord = None
                last_move_time = 0
                while self.running:
                    if self.inspect_mode:
                        idle_for = time.monotonic() - self.last_mouse_move_ts
                        if idle_for >= INSPECT_MOUSE_IDLE_TIMEOUT_SECONDS:  # type: ignore
                            self._exit_inspect_mode(
                                f"鼠标 {INSPECT_MOUSE_IDLE_TIMEOUT_SECONDS:g}s 未移动"
                            )

                    with self.coord_lock:
                        coord = self.latest_coord
                        self.latest_coord = None
                    if coord is not None:
                        pending_coord = coord
                        last_move_time = time.time()

                    if not self.inspect_mode:
                        if pending_coord is not None:
                            pending_coord = None
                            self.highlight.clear()
                            with self.control_lock:
                                self.current_control = None
                        time.sleep(NON_INSPECT_SLEEP) # type: ignore
                        continue

                    now = time.time()
                    if (pending_coord is not None and
                            (now - last_move_time) >= HOVER_DELAY and # type: ignore
                            pending_coord != self.last_processed_coord):
                        x, y = pending_coord
                        try:
                            self.highlight.clear()
                            time.sleep(CLEAR_DELAY) # type: ignore

                            # 探查模式下遮罩层会挡住命中，短暂隐藏以获取真实控件
                            overlay_hidden = False
                            try:
                                try:
                                    self.overlay.hide()
                                    overlay_hidden = True
                                    time.sleep(0.01)
                                except Exception:
                                    overlay_hidden = False

                                # 1. 向鼠标悬停位置强索 COM 接口，保证 UIA 数据鲜活
                                self._wake_up_com_interface(x, y)
                                time.sleep(0.2) # 给予毫秒级的内存对象同步时间

                                # 2. 原生 UIA 寻路机制
                                control = get_deepest_control(x, y, self.highlight.get_pid())
                            finally:
                                if overlay_hidden and self.inspect_mode:
                                    try:
                                        self.overlay.show()
                                    except Exception:
                                        pass

                            # ======== 更新高亮框 ========
                            if control:
                                rect = control.BoundingRectangle
                                if rect and rect.width() > 0 and rect.height() > 0:
                                    self.highlight.update(rect.left, rect.top,
                                                          rect.width(), rect.height())
                                with self.control_lock:
                                    self.current_control = control
                                self.last_processed_coord = pending_coord
                            else:
                                self.highlight.clear()
                                with self.control_lock:
                                    self.current_control = None
                                self.last_processed_coord = pending_coord

                        except Exception as e:
                            pending_coord = None
                            with self.control_lock:
                                self.current_control = None

                    time.sleep(LOOP_SLEEP) # type: ignore
        except Exception as e:
            print(f"[UI探测] 初始化失败: {e}")
        finally:
            print("[UI探测] 线程退出")

    def run(self):
        print("UI 探测工具（Ctrl+鼠标左键打印当前高亮控件信息，无需管理员权限）")
        print("命令: 1 - 开启探查模式, 2 - 关闭, clear - 清除高亮, wq - 退出")
        print("使用方法：")
        print(" - 开启后，鼠标悬停 0.8 秒 -> 红色高亮框")
        print(" - 按住 Ctrl 并鼠标左键点击 -> 打印当前高亮控件的完整信息（包括父级链）")

        time.sleep(0.5)

        self.keyboard.start()
        self.mouse_move.start()
        self.overlay.start()

        uia_thread = threading.Thread(target=self._uia_worker, daemon=True)
        uia_thread.start()

        # 默认进入探查模式（首次运行无需再输入 1）
        self.inspect_mode = True
        self.last_mouse_move_ts = time.monotonic()
        # 遮罩仅在按住 Ctrl 时出现并拦截点击
        print("探查模式已默认开启 → 移动鼠标至目标控件等待高亮；按住 Ctrl 再左键可抓取（不会触发应用点击）")

        try:
            while self.running:
                user_input = input("\n>>> ").strip().lower()
                if user_input == "wq":
                    print("正在退出...")
                    self.running = False
                    break
                elif user_input == "1":
                    self.inspect_mode = True
                    self.last_mouse_move_ts = time.monotonic()
                    # 遮罩仅在按住 Ctrl 时出现并拦截点击
                    print("探查模式已开启 → 移动鼠标至目标控件等待高亮；按住 Ctrl 再左键可抓取（不会触发应用点击）")
                elif user_input == "2":
                    self._exit_inspect_mode("用户手动关闭")
                elif user_input == "clear":
                    self.highlight.clear()
                    with self.control_lock:
                        self.current_control = None
                    print("已清除高亮")
        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            self.running = False
            self.highlight.stop()
            self.keyboard.stop()
            self.mouse_move.stop()
            self.overlay.stop()
            uia_thread.join(2)
            print("探针服务已终止。")