import psutil
import win32gui
import win32process
import win32con
from enum import Enum

class AutomationTech(Enum):
    PURE_UIA = "Pure UIA"
    PURE_MSAA = "Pure MSAA"
    MSAA_PROXY = "MSAA via UIA Proxy"
    HYBRID = "Hybrid"
    UNKNOWN = "Unknown"

class AppEra(Enum):
    MODERN = "Modern"
    TRANSITIONAL = "Transitional"
    LEGACY = "Legacy"
    UNKNOWN = "Unknown"

def get_process_info(pid):
    """获取进程详细信息"""
    try:
        process = psutil.Process(pid)
        
        info = {
            'name': process.name(),
            'exe': process.exe(),
            'create_time': process.create_time(),
            'modules': []
        }
        
        # 尝试获取模块（判断技术栈的关键）
        try:
            for module in process.memory_maps():
                module_name = module.path.split('\\')[-1].lower()
                info['modules'].append(module_name)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            info['modules'] = ["AccessDenied"]
        
        return info
    except psutil.NoSuchProcess:
        return None
    
def detect_by_modules(modules):
    """通过模块判断技术栈"""
    modules_set = set(modules)
    
    # 现代应用特征
    modern_signs = {
        'wpfgfx_cor3.dll': 'WPF (.NET Core)',
        'wpfgfx_v0400.dll': 'WPF (.NET Framework)',
        'windows.ui.xaml.dll': 'UWP',
        'microsoft.ui.xaml.dll': 'WinUI 3',
        'coreclr.dll': '.NET Core/5+',
        'clrjit.dll': '.NET (JIT)',
    }
    
    # 遗留应用特征
    legacy_signs = {
        'mfc140.dll': 'MFC 14',
        'mfc120.dll': 'MFC 12',
        'mfc100.dll': 'MFC 10',
        'mfc90.dll': 'MFC 9',
        'mfc80.dll': 'MFC 8',
        'msvcrt.dll': 'MSVC Runtime',
        'comctl32.dll': 'Common Controls',
    }
    
    found_modern = []
    found_legacy = []
    
    for mod, desc in modern_signs.items():
        if mod in modules_set:
            found_modern.append(desc)
    
    for mod, desc in legacy_signs.items():
        if mod in modules_set:
            found_legacy.append(desc)
    
    return {
        'modern': found_modern,
        'legacy': found_legacy,
        'is_modern': len(found_modern) > 0,
        'is_legacy': len(found_legacy) > 0
    }



def get_window_class_info(hwnd):
    """获取窗口类名信息"""
    if not win32gui.IsWindow(hwnd):
        return None
    
    # 获取类名
    class_name = win32gui.GetClassName(hwnd)
    
    # 获取窗口文本
    try:
        text = win32gui.GetWindowText(hwnd)
    except:
        text = ""
    
    # 判断技术栈
    tech_hints = []
    
    # WPF 特征
    if 'HwndWrapper' in class_name or 'Presentation' in class_name:
        tech_hints.append('WPF')
    
    # UWP/现代应用特征
    elif 'Windows.UI.Core' in class_name or 'ApplicationFrameWindow' in class_name:
        tech_hints.append('UWP/Modern')
    
    # WinForms 特征
    elif 'WindowsForms' in class_name:
        tech_hints.append('WinForms')
    
    # Win32 标准控件
    elif class_name in ['#32770', 'Edit', 'Button', 'Static', 'ComboBox', 
                        'ListBox', 'SysListView32', 'SysTreeView32']:
        tech_hints.append('Standard Win32')
    
    # MFC 特征
    elif class_name.startswith('Afx:') or 'Mfc' in class_name:
        tech_hints.append('MFC')
    
    else:
        tech_hints.append('Custom/Unknown')
    
    return {
        'class_name': class_name,
        'window_text': text,
        'tech_hints': tech_hints
    }


# 更新 main 函数
def main(ProcessId, NativeWindowHandle):
    print(f"输入参数:")
    print(f"  ProcessId: {ProcessId}")
    print(f"  NativeWindowHandle: {hex(NativeWindowHandle)} ({NativeWindowHandle})")
    print("=" * 50)
    
    # 1. 获取进程信息
    proc_info = get_process_info(ProcessId)
    if not proc_info:
        print("错误：无法获取进程信息")
        return
    
    print(f"[进程信息]")
    print(f"  名称: {proc_info['name']}")
    print(f"  路径: {proc_info['exe']}")
    print("-" * 50)
    
    # 2. 通过模块判断
    tech_by_module = detect_by_modules(proc_info['modules'])
    print(f"[模块分析]")
    print(f"  现代技术: {tech_by_module['modern'] or '未检测到'}")
    print(f"  遗留技术: {tech_by_module['legacy'] or '未检测到'}")
    print("-" * 50)
    
    # 3. 获取窗口类信息
    win_info = get_window_class_info(NativeWindowHandle)
    if win_info:
        print(f"[窗口信息]")
        print(f"  类名: {win_info['class_name']}")
        print(f"  标题: {win_info['window_text'][:50]}...")
        print(f"  技术提示: {win_info['tech_hints']}")
        print("=" * 50)
    else:
        print("错误：无效的窗口句柄")
    
    
if __name__ == "__main__":
    pid = 23948
    WinHandle = 0x5702B4
    
    main(pid, WinHandle)