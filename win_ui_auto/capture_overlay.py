import ctypes
import traceback
import time
from ctypes import wintypes
import threading

from constants import CAPTURE_OVERLAY_CLASS


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 64 位下真实 HWND 可能超过 2^31-1，不能用 c_long 承载，否则 ShowWindow/SetWindowLongW 报 OverflowError
HWND_PTR = ctypes.c_void_p


def _hwnd_ptr(h):
    if h is None:
        return HWND_PTR(None)
    return HWND_PTR(int(h))


WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

SW_SHOW = 5
SW_HIDE = 0

WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_LBUTTONDOWN = 0x0201
WM_KEYDOWN = 0x0100
WM_TIMER = 0x0113
WM_APP = 0x8000
# 由其它线程调用 show() 时，通过 SendMessage 在创建 HWND 的线程里执行 SetWindowLong（避免跨线程无效）
WM_WUIA_OVERLAY_APPLY_SOLID = WM_APP + 63

VK_CONTROL = 0x11

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

HCURSOR = getattr(wintypes, "HCURSOR", wintypes.HANDLE)
HICON = getattr(wintypes, "HICON", wintypes.HANDLE)
HBRUSH = getattr(wintypes, "HBRUSH", wintypes.HANDLE)
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)

GWL_EXSTYLE = -20
TIMER_ID_CTRL = 1
# 略短于 30ms，减少「松开 Ctrl 后立刻再按 Ctrl+左键」时遮罩尚未 Show 的窗口期
TIMER_INTERVAL_MS = 16

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


def _get_virtual_screen_rect():
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, w, h


class CaptureOverlay:
    """
    全屏透明遮罩（仅探查开启且按住 Ctrl 时存在 HWND）：
    - 松开 Ctrl：立即 DestroyWindow，不在 UIA 树中残留 WinUiAuto_CaptureOverlay
    - 按住 Ctrl：创建/显示遮罩并拦截；Ctrl+左键触发 on_capture()
    - hide/show：仅 SW_HIDE/SW_SHOW，供悬停命中测试短暂移开遮罩，不销毁窗口
    """

    def __init__(self, is_enabled, on_capture, debug_print=None):
        self._is_enabled = is_enabled
        self._on_capture = on_capture
        self._debug = debug_print or (lambda *_: None)

        self._hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._stop = threading.Event()

        self._wndproc_ref = None
        self._click_through = True

        # 显式签名（稳定性）
        user32.GetKeyState.argtypes = [ctypes.c_int]
        user32.GetKeyState.restype = wintypes.SHORT

        user32.DefWindowProcW.argtypes = [HWND_PTR, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        user32.ShowWindow.argtypes = [HWND_PTR, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL

        user32.ShowWindowAsync.argtypes = [HWND_PTR, ctypes.c_int]
        user32.ShowWindowAsync.restype = wintypes.BOOL

        user32.SendMessageW.argtypes = [HWND_PTR, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = LRESULT

        user32.SetLayeredWindowAttributes.argtypes = [HWND_PTR, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
        user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

        user32.PostMessageW.argtypes = [HWND_PTR, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL

        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int

        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL

        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = user32.DefWindowProcW.restype

        user32.GetWindowLongW.argtypes = [HWND_PTR, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [HWND_PTR, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowPos.argtypes = [
            HWND_PTR,
            HWND_PTR,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL

        # wintypes 在不同 Python/Windows 版本下不一定有 UINT_PTR，这里用 size_t 兼容
        UINT_PTR = ctypes.c_size_t
        user32.SetTimer.argtypes = [HWND_PTR, UINT_PTR, wintypes.UINT, wintypes.LPVOID]
        user32.SetTimer.restype = UINT_PTR
        user32.KillTimer.argtypes = [HWND_PTR, UINT_PTR]
        user32.KillTimer.restype = wintypes.BOOL

        user32.DestroyWindow.argtypes = [HWND_PTR]
        user32.DestroyWindow.restype = wintypes.BOOL

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)

    def stop(self):
        self._stop.set()
        h = self._hwnd
        if h:
            try:
                # 必须在创建 HWND 的线程里 DestroyWindow；跨线程投递 WM_CLOSE 由 wndproc 销毁
                user32.PostMessageW(_hwnd_ptr(h), WM_CLOSE, 0, 0)
            except Exception:
                pass
        try:
            if self._thread:
                self._thread.join(timeout=1.5)
        except Exception:
            pass

    def show(self):
        """可从任意线程调用：ShowWindowAsync + SendMessage 在遮罩线程上摘掉 WS_EX_TRANSPARENT。"""
        if not self._hwnd:
            return
        hp = _hwnd_ptr(self._hwnd)
        user32.ShowWindowAsync(hp, SW_SHOW)
        user32.SendMessageW(hp, WM_WUIA_OVERLAY_APPLY_SOLID, 0, 0)

    def hide(self):
        """可从任意线程调用：异步隐藏，避免 UIA 线程直接 ShowWindow 导致仍命中全屏遮罩。"""
        if self._hwnd:
            user32.ShowWindowAsync(_hwnd_ptr(self._hwnd), SW_HIDE)

    def _ctrl_down(self) -> bool:
        try:
            return (user32.GetKeyState(VK_CONTROL) & 0x8000) != 0
        except Exception:
            return False

    def _set_click_through(self, hwnd, enabled: bool):
        """enabled=True: 鼠标穿透（普通点击直接落到目标应用）"""
        try:
            hp = _hwnd_ptr(hwnd)
            ex_raw = int(user32.GetWindowLongW(hp, GWL_EXSTYLE))
            ex_u = ex_raw & 0xFFFFFFFF
            if enabled:
                new_u = ex_u | WS_EX_TRANSPARENT
            else:
                new_u = ex_u & (~WS_EX_TRANSPARENT) & 0xFFFFFFFF
            if new_u == ex_u:
                return
            # SetWindowLongW 第三参为有符号 LONG，需把 DWORD 样式折叠到 32 位有符号范围
            new_signed = new_u if new_u < 0x80000000 else new_u - 0x100000000
            user32.SetWindowLongW(hp, GWL_EXSTYLE, new_signed)
            user32.SetWindowPos(
                hp,
                HWND_PTR(None),
                0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
            self._click_through = enabled
        except Exception:
            pass

    def _run(self):
        h_instance = kernel32.GetModuleHandleW(None)
        class_name = CAPTURE_OVERLAY_CLASS

        WNDPROCTYPE = ctypes.WINFUNCTYPE(
            user32.DefWindowProcW.restype,
            HWND_PTR,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_CLOSE:
                    user32.DestroyWindow(_hwnd_ptr(hwnd))
                    return 0

                if msg == WM_WUIA_OVERLAY_APPLY_SOLID:
                    self._set_click_through(hwnd, False)
                    return 0

                if msg == WM_TIMER and wparam == TIMER_ID_CTRL:
                    enabled = False
                    try:
                        enabled = bool(self._is_enabled())
                    except Exception:
                        enabled = False
                    hpw = _hwnd_ptr(hwnd)
                    ctrl = self._ctrl_down()

                    # 探查关闭或进程退出：销毁，外层循环下次 Ctrl 再 CreateWindow
                    if self._stop.is_set() or not enabled:
                        try:
                            user32.DestroyWindow(hpw)
                        except Exception:
                            pass
                        return 0

                    # 探查仍开启：按住 Ctrl 时置顶拦截；松开 Ctrl 只隐藏+穿透，保留 HWND，
                    # 避免反复 Destroy/Create 与悬停线程 hide/show 竞态导致第二次 Ctrl+左键穿透。
                    if ctrl:
                        try:
                            user32.ShowWindow(hpw, SW_SHOW)
                        except Exception:
                            pass
                        if self._click_through:
                            self._set_click_through(hwnd, False)
                    else:
                        try:
                            self._set_click_through(hwnd, True)
                        except Exception:
                            pass
                        try:
                            user32.ShowWindow(hpw, SW_HIDE)
                        except Exception:
                            pass
                    return 0

                if msg == WM_LBUTTONDOWN:
                    enabled = False
                    try:
                        enabled = bool(self._is_enabled())
                    except Exception:
                        enabled = False

                    # 探测模式下：仅 Ctrl+左键拦截并触发抓取；普通点击应穿透到目标应用
                    if enabled and self._ctrl_down():
                        try:
                            self._on_capture()
                        except Exception:
                            try:
                                self._debug(traceback.format_exc())
                            except Exception:
                                pass
                        return 0

                if msg == WM_DESTROY:
                    try:
                        try:
                            user32.KillTimer(_hwnd_ptr(hwnd), TIMER_ID_CTRL)
                        except Exception:
                            pass
                        self._hwnd = None
                        if self._stop.is_set():
                            user32.PostQuitMessage(0)
                    except Exception:
                        pass
                    return 0

                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            except Exception:
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROCTYPE(wndproc)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROCTYPE),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", HICON),
                ("hCursor", HCURSOR),
                ("hbrBackground", HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        wc = WNDCLASS()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = h_instance
        wc.hIcon = 0
        wc.hCursor = 0
        wc.hbrBackground = 0
        wc.lpszMenuName = None
        wc.lpszClassName = class_name

        try:
            user32.RegisterClassW(ctypes.byref(wc))
        except Exception:
            # 已注册也没关系
            pass

        self._ready.set()

        x, y, w, h = _get_virtual_screen_rect()
        ex_style = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED
        style = WS_POPUP

        while not self._stop.is_set():
            while not self._stop.is_set():
                try:
                    if bool(self._is_enabled()) and self._ctrl_down():
                        break
                except Exception:
                    pass
                time.sleep(0.02)

            if self._stop.is_set():
                break

            hwnd = user32.CreateWindowExW(
                ex_style,
                class_name,
                "CaptureOverlay",
                style,
                x,
                y,
                w,
                h,
                0,
                0,
                h_instance,
                0,
            )
            if not hwnd:
                time.sleep(0.05)
                continue

            self._hwnd = hwnd
            LWA_ALPHA = 0x2
            hp = _hwnd_ptr(hwnd)
            user32.SetLayeredWindowAttributes(hp, 0, 1, LWA_ALPHA)
            self._set_click_through(hwnd, False)
            try:
                user32.SetTimer(hp, TIMER_ID_CTRL, TIMER_INTERVAL_MS, 0)
            except Exception:
                pass
            user32.ShowWindow(hp, SW_SHOW)

            msg = wintypes.MSG()
            while not self._stop.is_set():
                r = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if r == 0:
                    break
                if r == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                if not self._hwnd:
                    break

            self._hwnd = None

