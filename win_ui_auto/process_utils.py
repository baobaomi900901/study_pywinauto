# win_ui_auto/process_utils.py
import ctypes
import ctypes.wintypes

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MAX_PATH = 260

kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
user32 = ctypes.windll.user32


def hwnd_c_void_p(hwnd):
    """把 Python 里的 HWND 整型包装为 ctypes.c_void_p，避免 64 位句柄被当成 c_int 溢出。"""
    if hwnd is None:
        return ctypes.c_void_p(None)
    if isinstance(hwnd, ctypes.c_void_p):
        return hwnd
    try:
        v = int(hwnd)
    except (TypeError, ValueError):
        return ctypes.c_void_p(None)
    if v == 0:
        return ctypes.c_void_p(None)
    return ctypes.c_void_p(v)


def get_window_class_name(hwnd) -> str:
    """读取窗口类名（64 位 HWND 安全）。"""
    hp = hwnd_c_void_p(hwnd)
    if not hp.value:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    try:
        n = user32.GetClassNameW(hp, buf, 256)
        return buf.value if n else ""
    except Exception:
        return ""


def get_process_name(pid):
    """通过 PID 获取进程名称（带缓存）"""
    if not hasattr(get_process_name, "cache"):
        get_process_name.cache = {}
    if pid in get_process_name.cache:
        return get_process_name.cache[pid]
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            return None
        try:
            name_buffer = ctypes.create_unicode_buffer(MAX_PATH)
            size = ctypes.c_uint(MAX_PATH)
            if psapi.GetModuleBaseNameW(handle, None, name_buffer, size):
                name = name_buffer.value
            elif psapi.GetProcessImageFileNameW(handle, name_buffer, size):
                full_path = name_buffer.value
                name = full_path.split('\\')[-1] if '\\' in full_path else full_path
            else:
                name = None
            if name:
                get_process_name.cache[pid] = name
            return name
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def cleanup_stale_ui_tool_windows(log=None):
    """
    启动时清理上次异常退出遗留的：Ctrl 探测遮罩（WinUiAuto_CaptureOverlay）、
    Tk 高亮框（标题 WinUiAuto_HighlightOverlay）。仅 PostMessage WM_CLOSE，不跨线程 DestroyWindow。
    """
    import time

    from constants import CAPTURE_OVERLAY_CLASS, HIGHLIGHT_TOPLEVEL_TITLE

    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    closed = []

    @ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )
    def _enum(hwnd, _lparam):
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            cls = buf.value or ""
            # 待机隐藏的遮罩不可见，仍需能清理
            if cls == CAPTURE_OVERLAY_CLASS:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                closed.append(("overlay", hwnd))
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            if cls == "TkTopLevel":
                tbuf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, tbuf, 512)
                title = (tbuf.value or "").strip()
                if title == HIGHLIGHT_TOPLEVEL_TITLE:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    closed.append(("highlight", hwnd))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(_enum, 0)
    except Exception:
        pass
    if closed and log:
        try:
            log(f"[cleanup] WM_CLOSE 遗留窗口: {closed}")
        except Exception:
            pass
    if closed:
        time.sleep(0.08)