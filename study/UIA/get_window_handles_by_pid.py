# 通过 pid 去获取窗口句柄, 或者主窗口句柄

import ctypes
import ctypes.wintypes

# 定义 Windows API
EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
IsWindowVisible = ctypes.windll.user32.IsWindowVisible

def get_window_text(hwnd):
    """通过 ctypes 获取窗口标题"""
    GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
    GetWindowTextW = ctypes.windll.user32.GetWindowTextW
    length = GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def get_window_handles_by_pid(pid: int, visible_only: bool = True) -> list:
    """
    通过进程 ID 获取该进程所有顶层窗口的句柄列表（ctypes 实现）。
    适用于 Win32 和 UIA 应用程序（因为它们都有顶层 HWND）。

    :param pid: 进程 ID
    :param visible_only: 是否只返回可见窗口，默认为 True
    :return: 窗口句柄列表（可能为空）
    """
    handles = []

    def enum_callback(hwnd, lparam):
        process_id = ctypes.wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == pid:
            if not visible_only or IsWindowVisible(hwnd):
                handles.append(hwnd)
        return True  # 继续枚举

    callback = EnumWindowsProc(enum_callback)
    EnumWindows(callback, 0)
    return handles


def get_main_window_handles_by_pid(pid: int) -> list:
    all_hwnds = get_window_handles_by_pid(pid, visible_only=True)
    main_hwnds = []
    for hwnd in all_hwnds:
        title = get_window_text(hwnd)
        if title:
            main_hwnds.append(hwnd)
    return main_hwnds

# 示例用法
if __name__ == '__main__':
    pid = 4300
    hwnds = get_window_handles_by_pid(pid)
    print(f"找到的窗口句柄: {[hex(h) for h in hwnds]}")

    hwnds2 = get_main_window_handles_by_pid(pid)
    print(f"找到的窗口句柄: {[hex(h) for h in hwnds2]}")