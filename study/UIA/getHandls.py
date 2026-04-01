# 通过 PID 去查询句柄号

import uiautomation as auto

def get_native_handle_from_pid(pid):
    """
    通过 PID 获取 NativeWindowHandle（就是 Inspect 里的句柄）
    支持 Win32 / WPF / Qt / Electron 全部软件
    """
    root = auto.GetRootControl()
    
    for window in root.GetChildren():
        try:
            if window.ProcessId == pid:
                # ✅ 关键：从 UIA 元素里提取原生窗口句柄
                handle = window.NativeWindowHandle
                return handle, window.Name
        except:
            continue
    return None, None

# ======================
# 使用（你的 WinSCP）
# ======================
pid = 23948  # 你的进程号
hwnd, title = get_native_handle_from_pid(pid)

if hwnd:
    print(f"✅ 成功获取 NativeWindowHandle")
    print(f"窗口标题: {title}")
    print(f"十六进制句柄: {hex(hwnd)}")  # <-- 这个就是 0x5702B4
else:
    print("❌ 未找到")