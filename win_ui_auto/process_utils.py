# win_ui_auto/process_utils.py
import ctypes
import ctypes.wintypes

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MAX_PATH = 260

kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

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