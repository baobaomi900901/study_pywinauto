import ctypes
from ctypes import wintypes
import threading


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

SW_SHOW = 5
SW_HIDE = 0

WM_DESTROY = 0x0002
WM_LBUTTONDOWN = 0x0201
WM_KEYDOWN = 0x0100
WM_TIMER = 0x0113
WM_APP = 0x8000

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
TIMER_INTERVAL_MS = 30

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
    全屏透明遮罩窗口：
    - 探测模式开启时显示，吃掉所有鼠标点击（目标应用收不到）
    - Ctrl + 左键时触发 on_capture()
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

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL

        user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
        user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL

        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int

        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL

        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = user32.DefWindowProcW.restype

        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL

        # wintypes 在不同 Python/Windows 版本下不一定有 UINT_PTR，这里用 size_t 兼容
        UINT_PTR = ctypes.c_size_t
        user32.SetTimer.argtypes = [wintypes.HWND, UINT_PTR, wintypes.UINT, wintypes.LPVOID]
        user32.SetTimer.restype = UINT_PTR
        user32.KillTimer.argtypes = [wintypes.HWND, UINT_PTR]
        user32.KillTimer.restype = wintypes.BOOL

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
        if self._hwnd:
            try:
                user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)
            except Exception:
                pass
        try:
            if self._thread:
                self._thread.join(timeout=1.5)
        except Exception:
            pass

    def show(self):
        if self._hwnd:
            user32.ShowWindow(self._hwnd, SW_SHOW)

    def hide(self):
        if self._hwnd:
            user32.ShowWindow(self._hwnd, SW_HIDE)

    def _ctrl_down(self) -> bool:
        try:
            return (user32.GetKeyState(VK_CONTROL) & 0x8000) != 0
        except Exception:
            return False

    def _set_click_through(self, hwnd, enabled: bool):
        """enabled=True: 鼠标穿透（普通点击直接落到目标应用）"""
        try:
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                new_style = ex_style | WS_EX_TRANSPARENT
            else:
                new_style = ex_style & (~WS_EX_TRANSPARENT)
            if new_style == ex_style:
                return
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            user32.SetWindowPos(
                hwnd,
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
        class_name = "WinUiAuto_CaptureOverlay"

        WNDPROCTYPE = ctypes.WINFUNCTYPE(
            user32.DefWindowProcW.restype,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_TIMER and wparam == TIMER_ID_CTRL:
                    enabled = False
                    try:
                        enabled = bool(self._is_enabled())
                    except Exception:
                        enabled = False

                    # 设计目标：
                    # - 探查模式开启时：只有按住 Ctrl 才出现遮罩并拦截点击（目标应用不触发点击）
                    # - 未按 Ctrl：遮罩隐藏，不影响目标应用的任何点击
                    if enabled and self._ctrl_down():
                        try:
                            user32.ShowWindow(hwnd, SW_SHOW)
                        except Exception:
                            pass
                        # 显示时需要拦截点击
                        if self._click_through:
                            self._set_click_through(hwnd, False)
                    else:
                        # 未启用或未按 Ctrl：隐藏遮罩并保持穿透
                        try:
                            user32.ShowWindow(hwnd, SW_HIDE)
                        except Exception:
                            pass
                        if not self._click_through:
                            self._set_click_through(hwnd, True)
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
                            pass
                        return 0

                if msg == WM_DESTROY:
                    try:
                        try:
                            user32.KillTimer(hwnd, TIMER_ID_CTRL)
                        except Exception:
                            pass
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

        x, y, w, h = _get_virtual_screen_rect()
        ex_style = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED
        style = WS_POPUP

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

        self._hwnd = hwnd
        # 1% 不透明度：几乎不可见，但仍能接收鼠标事件
        LWA_ALPHA = 0x2
        user32.SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)

        # 默认鼠标穿透：不影响目标应用正常点击（仅 Ctrl+点击才需要拦截）
        self._set_click_through(hwnd, True)

        # 定时检测 Ctrl 状态以动态切换穿透
        try:
            user32.SetTimer(hwnd, TIMER_ID_CTRL, TIMER_INTERVAL_MS, 0)
        except Exception:
            pass

        user32.ShowWindow(hwnd, SW_HIDE)
        self._ready.set()

        msg = wintypes.MSG()
        while not self._stop.is_set():
            r = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if r == 0 or r == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

