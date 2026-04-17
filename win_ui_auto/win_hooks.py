# win_ui_auto/win_hooks.py
import ctypes
from ctypes import wintypes
import threading


WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_QUIT = 0x0012
VK_CONTROL = 0x11

# ctypes.wintypes 在不同 Python 版本/实现里不一定提供 LRESULT/HHOOK
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)  # LONG_PTR
HHOOK = getattr(wintypes, "HHOOK", wintypes.HANDLE)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


LowLevelMouseProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class LowLevelMouseHook:
    """
    Windows 低级鼠标钩子（WH_MOUSE_LL）。

    - 在回调中可以 return 1 来“吞掉”鼠标事件，阻止目标应用收到点击。
    - 只建议在需要拦截的短时间窗口内启用（例如探测模式）。
    """

    def __init__(self, is_enabled, on_trigger, debug_print=None, swallow_all_left_click_when_enabled=True):
        self._is_enabled = is_enabled
        self._on_trigger = on_trigger
        self._debug = debug_print or (lambda *_: None)
        self._swallow_all_left_click_when_enabled = swallow_all_left_click_when_enabled

        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

        # 显式声明函数签名，避免 Python 3.11+ 上的回调类型校验报错
        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,          # idHook
            LowLevelMouseProc,     # lpfn
            wintypes.HINSTANCE,    # hMod
            wintypes.DWORD,        # dwThreadId
        ]
        self._user32.SetWindowsHookExW.restype = HHOOK

        self._user32.UnhookWindowsHookEx.argtypes = [HHOOK]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        self._user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.CallNextHookEx.restype = LRESULT

        self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self._user32.GetAsyncKeyState.restype = wintypes.SHORT

        self._user32.GetKeyState.argtypes = [ctypes.c_int]
        self._user32.GetKeyState.restype = wintypes.SHORT

        self._user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.PostThreadMessageW.restype = wintypes.BOOL

        self._user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self._user32.GetMessageW.restype = ctypes.c_int

        self._user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        self._user32.TranslateMessage.restype = wintypes.BOOL

        self._user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        self._user32.DispatchMessageW.restype = LRESULT

        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        self._kernel32.GetCurrentThreadId.argtypes = []
        self._kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        self._hook = None
        self._hook_thread = None
        self._hook_thread_id = None
        self._proc_ref = None  # 防止 callback 被 GC

        self._stop_evt = threading.Event()
        self._triggered_guard = False  # 防抖：按住 Ctrl 连点时避免重复触发过快
        self._swallow_left_click = False  # 吞掉一次完整的 left click（down+up）

    def start(self):
        if self._hook_thread and self._hook_thread.is_alive():
            return
        self._stop_evt.clear()
        self._hook_thread = threading.Thread(target=self._run, daemon=True)
        self._hook_thread.start()

    def stop(self):
        self._stop_evt.set()
        # 让消息循环退出
        try:
            if self._hook_thread_id:
                self._user32.PostThreadMessageW(self._hook_thread_id, WM_QUIT, 0, 0)
        except Exception:
            pass
        try:
            if self._hook_thread:
                self._hook_thread.join(timeout=1.5)
        except Exception:
            pass

    def _run(self):
        self._hook_thread_id = self._kernel32.GetCurrentThreadId()

        def is_ctrl_down():
            try:
                # 与 Delphi 版本一致：GetKeyState 高位为 1 表示按下
                return (self._user32.GetKeyState(VK_CONTROL) & 0x8000) != 0
            except Exception:
                return False

        def callback(nCode, wParam, lParam):
            try:
                if nCode == 0 and wParam in (WM_LBUTTONDOWN, WM_LBUTTONDBLCLK):
                    enabled = False
                    try:
                        enabled = bool(self._is_enabled())
                    except Exception:
                        enabled = False

                    # 只要处于探测模式就吞掉左键，避免任何目标控件收到点击（更稳）
                    # 触发抓取仍需 Ctrl 按下
                    if enabled and self._swallow_all_left_click_when_enabled:
                        if is_ctrl_down():
                            try:
                                if not self._triggered_guard:
                                    self._triggered_guard = True
                                    self._on_trigger()
                            finally:
                                self._swallow_left_click = True
                                if DEBUG:
                                    self._debug(f"[hook] swallowed {hex(int(wParam))} (enabled)")
                                return 1  # 非 0：拦截（标准写法）
                        else:
                            self._swallow_left_click = True
                            if DEBUG:
                                self._debug(f"[hook] swallowed {hex(int(wParam))} (enabled, no-ctrl)")
                            return 1  # 非 0：拦截（标准写法）

                    if enabled and is_ctrl_down():
                        # 触发抓取（在吞掉点击前触发）
                        try:
                            if not self._triggered_guard:
                                self._triggered_guard = True
                                self._on_trigger()
                        finally:
                            # 吞掉本次点击，避免目标控件触发点击事件
                            self._swallow_left_click = True
                            return 1  # 非 0：拦截（标准写法）

                # Ctrl+左键被吞掉后，有些程序在 mouse-up 上仍可能触发行为，因此 mouse-up 也一并吞掉
                if nCode == 0 and wParam == WM_LBUTTONUP:
                    enabled = False
                    try:
                        enabled = bool(self._is_enabled())
                    except Exception:
                        enabled = False

                    if enabled and self._swallow_all_left_click_when_enabled:
                        # 如果之前吞了 down，这里一定要吞 up，形成完整的“无点击”
                        if self._swallow_left_click:
                            self._swallow_left_click = False
                        if DEBUG:
                            self._debug("[hook] swallowed WM_LBUTTONUP (enabled)")
                        return 1  # 非 0：拦截（标准写法）

                    if self._swallow_left_click:
                        self._swallow_left_click = False
                        return 1  # 非 0：拦截（标准写法）
                    # 兜底：如果这次 up 没标记，但 Ctrl 仍按下且处于探测模式，也吞掉
                    if enabled and is_ctrl_down():
                        return 1  # 非 0：拦截（标准写法）

                return self._user32.CallNextHookEx(self._hook, nCode, wParam, lParam)
            except Exception:
                try:
                    return self._user32.CallNextHookEx(self._hook, nCode, wParam, lParam)
                except Exception:
                    return 0

        # 保持引用避免被回收
        self._proc_ref = LowLevelMouseProc(callback)

        # 安装 hook（WH_MOUSE_LL 不需要注入 DLL，hMod 可为当前模块句柄或 None）
        h_instance = self._kernel32.GetModuleHandleW(None)
        self._hook = self._user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc_ref, h_instance, 0)
        if not self._hook:
            self._debug("[hook] SetWindowsHookExW failed")
            return

        msg = wintypes.MSG()
        while not self._stop_evt.is_set():
            # GetMessageW 会阻塞；WM_QUIT 会让其返回 0
            r = self._user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if r == 0:
                break
            if r == -1:
                break

            # Ctrl 松开后解除防抖，允许下次 Ctrl+点击触发
            try:
                if (self._user32.GetKeyState(VK_CONTROL) & 0x8000) == 0:
                    self._triggered_guard = False
            except Exception:
                self._triggered_guard = False

            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

        try:
            if self._hook:
                self._user32.UnhookWindowsHookEx(self._hook)
        except Exception:
            pass
        self._hook = None

