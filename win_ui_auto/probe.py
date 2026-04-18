# ./win_ui_auto/probe.py
import sys
import queue
import threading
import time
import ctypes
import re # 新增正则库用于优化 XPath
from ctypes import wintypes
from constants import *
from highlight import HighlightWindow
from listeners import MouseMoveListener
from capture_overlay import CaptureOverlay
from control_info import get_deepest_control, get_control_info, print_control_info, write_control_info_to_file
from process_utils import get_window_class_name


def _probe_debug_print(msg: str):
    if DEBUG:
        print(msg, file=sys.stderr)


_clipboard_ctypes_ready = False


def _ensure_clipboard_ctypes():
    """64 位下 HGLOBAL 为指针宽度；默认 ctypes 原型按 c_int 会截断并在 GlobalLock 等处 Overflow。"""
    global _clipboard_ctypes_ready
    if _clipboard_ctypes_ready:
        return
    k = ctypes.windll.kernel32
    k.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    k.GlobalAlloc.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = (ctypes.c_void_p,)
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    k.GlobalUnlock.restype = wintypes.BOOL
    k.GlobalFree.argtypes = (ctypes.c_void_p,)
    k.GlobalFree.restype = ctypes.c_void_p
    u = ctypes.windll.user32
    u.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
    u.SetClipboardData.restype = ctypes.c_void_p
    _clipboard_ctypes_ready = True


def _set_clipboard_unicode(text: str) -> bool:
    """用 Win32 剪贴板写入 Unicode 文本（避免 Tk 跨线程问题）。"""
    _ensure_clipboard_ctypes()
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    if not user32.OpenClipboard(None):
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        raw = (text or "").encode("utf-16-le") + b"\x00\x00"
        size = len(raw)
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h_global:
            return False
        p = kernel32.GlobalLock(h_global)
        if not p:
            kernel32.GlobalFree(h_global)
            return False
        try:
            ctypes.memmove(p, raw, size)
        finally:
            kernel32.GlobalUnlock(h_global)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
            kernel32.GlobalFree(h_global)
            return False
        return True
    finally:
        user32.CloseClipboard()


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
        self._last_capture_mono = None
        self._capture_queue = queue.Queue(maxsize=8)

        self.highlight = HighlightWindow()
        self.mouse_move = MouseMoveListener(on_move=self._on_mouse_move)
        # 遮罩由 CaptureOverlay 管理：未按 Ctrl 时不挡点击；按住 Ctrl 时出现并拦截 Ctrl+左键
        self.overlay = CaptureOverlay(
            is_enabled=lambda: self.inspect_mode,
            on_capture=self._on_ctrl_click_capture,
            debug_print=_probe_debug_print if DEBUG else None,
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
        """【绝杀2】：强取 COM 接口，精准穿透透明防弹玻璃

        注意：不要改写 ctypes.windll.user32 的全局 argtypes/restype，否则会污染
        uiautomation 等库对同一函数的调用，并在 64 位 HWND 上触发 OverflowError。
        """
        user32 = ctypes.windll.user32
        oleacc = ctypes.windll.oleacc
        GA_ROOT = 2
        OBJID_CLIENT_DWORD = 0xFFFFFFFC

        try:
            xi, yi = int(x), int(y)
            pt = wintypes.POINT(xi, yi)
            hwnd_p = user32.WindowFromPoint(pt)
            hwnd_val = int(ctypes.cast(hwnd_p, ctypes.c_void_p).value or 0)
            if not hwnd_val:
                return

            root_p = user32.GetAncestor(ctypes.c_void_p(hwnd_val), GA_ROOT)
            root_val = int(ctypes.cast(root_p, ctypes.c_void_p).value or hwnd_val)

            target_vals = {hwnd_val, root_val}

            def enum_child_proc(h, lParam):
                cn = get_window_class_name(h)
                if cn == "Chrome_RenderWidgetHostHWND":
                    hv = int(ctypes.cast(h, ctypes.c_void_p).value or 0)
                    if hv:
                        target_vals.add(hv)
                return True

            EnumChildProcType = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.c_void_p, wintypes.LPARAM
            )
            self._wake_enum_cb_keepalive = EnumChildProcType(enum_child_proc)
            user32.EnumChildWindows(
                ctypes.c_void_p(root_val),
                self._wake_enum_cb_keepalive,
                0,
            )

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            IID_IAccessible = GUID(
                0x618736E0,
                0x3C3D,
                0x11CF,
                (0x81, 0x0C, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71),
            )

            for tv in list(target_vals):
                if not tv:
                    continue
                punk = ctypes.c_void_p()
                try:
                    oleacc.AccessibleObjectFromWindow(
                        ctypes.c_void_p(tv),
                        wintypes.DWORD(OBJID_CLIENT_DWORD),
                        ctypes.byref(IID_IAccessible),
                        ctypes.byref(punk),
                    )
                except Exception:
                    pass
        except Exception:
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

    @staticmethod
    def _screen_cursor_point():
        user32 = ctypes.windll.user32
        pt = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return None
        return int(pt.x), int(pt.y)

    def _control_under_screen_point(self, x, y):
        """遮罩置顶时不能用缓存的 current_control，必须在隐藏遮罩后按屏幕坐标重新命中。"""
        x, y = int(x), int(y)
        overlay_hidden = False
        try:
            try:
                self.overlay.hide()
                overlay_hidden = True
                # ShowWindowAsync 在遮罩线程排队生效，略等再 ElementFromPoint
                time.sleep(0.06)
            except Exception:
                overlay_hidden = False
            self._wake_up_com_interface(x, y)
            time.sleep(0.12)
            return get_deepest_control(x, y, self.highlight.get_pid())
        finally:
            if overlay_hidden and self.inspect_mode:
                try:
                    self.overlay.show()
                except Exception:
                    pass

    def _on_ctrl_click_capture(self):
        """在遮罩/Win32 消息线程上调用：只做入队，禁止在此线程调 UIA/COM。"""
        if not self.inspect_mode:
            return
        now = time.monotonic()
        if self._last_capture_mono is not None and now - self._last_capture_mono < 0.35:
            return
        self._last_capture_mono = now

        print("\n[抓取] Ctrl+左键，获取当前高亮控件信息...")
        pt = self._screen_cursor_point()
        if pt is None:
            print("→ 无法读取鼠标坐标。")
            return
        try:
            self._capture_queue.put_nowait(pt)
        except queue.Full:
            print("→ 抓取请求堆积，请稍后再试。")

    def _process_ctrl_capture(self, cx, cy):
        """仅在 _uia_worker（已 UIAutomationInitializerInThread）中调用。"""
        if not self.inspect_mode:
            return

        control = self._control_under_screen_point(cx, cy)
        if control is None:
            with self.control_lock:
                control = self.current_control

        if not control:
            print("→ 未能解析到控件：请将鼠标对准目标（可先悬停出红框）再 Ctrl+左键。")
            return

        rect = control.BoundingRectangle
        if not rect:
            print("→ 控件无边界矩形")
            return

        x = rect.left + rect.width() // 2
        y = rect.top + rect.height() // 2
        info = get_control_info(control, x, y, self.highlight.get_pid())

        if not info:
            print("→ 获取控件信息失败")
            return

        if 'xpath' in info:
            info['raw_xpath'] = info['xpath']
            pname = ""
            try:
                import psutil
                pname = psutil.Process(control.ProcessId).name().lower()
            except Exception:
                pass

            info['xpath'] = self._optimize_cef_xpath(info['xpath'], process_name=pname)

            xp = (info.get("xpath") or "").strip()
            if not xp:
                print(
                    "\n[提示] 当前命中为本工具探测遮罩 (CaptureOverlay)，未生成业务 XPath。"
                    "请将鼠标移到目标应用控件上再 Ctrl+左键（松开 Ctrl 后遮罩 HWND 已销毁，一般不会误点）。"
                )
            elif _set_clipboard_unicode(f'"{xp}"'):
                print("\n[辅助] XPath 已自动复制到系统剪贴板，直接 Ctrl+V 即可使用。")

        self.last_printed_id, self.last_print_time = print_control_info(
            info,
            self.last_printed_id,
            self.last_print_time,
            self.print_interval,
            force=True,
        )
        write_control_info_to_file(info)
        self._exit_inspect_mode("已抓取信息；如需继续请输入 1 重新开启")

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
                    # Ctrl+左键在 Win32 线程入队，必须在本线程执行 UIA/COM
                    latest_cap = None
                    while True:
                        try:
                            latest_cap = self._capture_queue.get_nowait()
                        except queue.Empty:
                            break
                    if latest_cap is not None:
                        self._process_ctrl_capture(latest_cap[0], latest_cap[1])

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
                                    time.sleep(0.05)
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
            if DEBUG:
                import traceback
                traceback.print_exc()
        finally:
            print("[UI探测] 线程退出")

    def run(self):
        print("UI 探测工具（Ctrl+鼠标左键打印当前高亮控件信息，无需管理员权限）")
        print("命令: 1 - 开启探查模式, 2 - 关闭, clear - 清除高亮, wq - 退出")
        print("使用方法：")
        print(" - 开启后，鼠标悬停 0.8 秒 -> 红色高亮框")
        print(" - 按住 Ctrl 并鼠标左键点击 -> 打印当前高亮控件的完整信息（包括父级链）")

        time.sleep(0.5)

        self.mouse_move.start()
        self.overlay.start()

        uia_thread = threading.Thread(target=self._uia_worker, daemon=True)
        uia_thread.start()

        # 默认进入探查模式（首次运行无需再输入 1）
        self.inspect_mode = True
        self.last_mouse_move_ts = time.monotonic()
        # 遮罩仅在按住 Ctrl 时创建并拦截点击；松开 Ctrl 即销毁 HWND
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
                    # 遮罩仅在按住 Ctrl 时创建；松开即销毁
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
            self.mouse_move.stop()
            self.overlay.stop()
            uia_thread.join(2)
            print("探针服务已终止。")