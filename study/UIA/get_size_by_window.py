import ctypes
import ctypes.wintypes

# ---------- Windows API 函数定义 ----------
EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
GetWindowTextW = ctypes.windll.user32.GetWindowTextW
IsIconic = ctypes.windll.user32.IsIconic

# 定义 RECT 结构体
class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.wintypes.LONG),
        ('top', ctypes.wintypes.LONG),
        ('right', ctypes.wintypes.LONG),
        ('bottom', ctypes.wintypes.LONG),
    ]

GetWindowRect = ctypes.windll.user32.GetWindowRect
GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(RECT)]
GetWindowRect.restype = ctypes.wintypes.BOOL

# ---------- 辅助函数 ----------
def get_window_text(hwnd):
    """通过 ctypes 获取窗口标题"""
    length = GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def get_window_rect(hwnd):
    """
    获取窗口在屏幕上的矩形区域（像素坐标）。
    :param hwnd: 窗口句柄
    :return: (left, top, right, bottom) 元组，失败返回 None
    """
    rect = RECT()
    if GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None

def get_window_position_and_size(hwnd):
    """
    获取窗口在屏幕上的位置和尺寸。
    :param hwnd: 窗口句柄
    :return: (x, y, width, height) 元组，失败返回 None
    """
    rect = get_window_rect(hwnd)
    if rect:
        left, top, right, bottom = rect
        return (left, top, right - left, bottom - top)
    return None

# ---------- 核心功能 ----------
def get_window_handles_by_pid(pid: int, visible_only: bool = True) -> list:
    """
    通过进程 ID 获取该进程所有顶层窗口的句柄列表（ctypes 实现）。
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
    """
    获取进程的主窗口句柄（有标题且可见）。
    """
    all_hwnds = get_window_handles_by_pid(pid, visible_only=True)
    main_hwnds = []
    for hwnd in all_hwnds:
        title = get_window_text(hwnd)
        if title:   # 有标题
            main_hwnds.append(hwnd)
    return main_hwnds

# ---------- 示例用法 ----------
if __name__ == '__main__':
    # 示例：假设进程 ID 为 23948（请替换为实际 PID）
    pid = 23948

    # 获取所有可见窗口句柄
    all_hwnds = get_window_handles_by_pid(pid)
    print(f"所有可见窗口句柄: {[hex(h) for h in all_hwnds]}")

    # 获取主窗口句柄（有标题）
    main_hwnds = get_main_window_handles_by_pid(pid)
    print(f"主窗口句柄: {[hex(h) for h in main_hwnds]}")

    # 对每个主窗口获取位置和尺寸
    for hwnd in main_hwnds:
        pos_size = get_window_position_and_size(hwnd)
        if pos_size:
            x, y, w, h = pos_size
            print(f"窗口 {hex(hwnd)} 位置: ({x}, {y}), 尺寸: {w} x {h}")

            # 可选：检查窗口是否最小化
            if IsIconic(hwnd):
                print("  注意：窗口当前已最小化，坐标可能不准确")
        else:
            print(f"无法获取窗口 {hex(hwnd)} 的矩形信息")