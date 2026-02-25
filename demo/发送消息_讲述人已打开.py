# disable_narrator.py
import winreg
import ctypes

def disable_narrator_on_startup():
    """在系统启动时禁用讲述人"""
    print("正在禁用讲述人...")
    
    try:
        # 设置RunningState为0
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                              r"Software\Microsoft\Narrator\NoRoam") as key:
            winreg.SetValueEx(key, "RunningState", 0, winreg.REG_DWORD, 0)
            print("已设置 RunningState = 0")
        
        # 设置narrator为0
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                              r"Software\Microsoft\Windows NT\CurrentVersion\AccessibilityTemp") as key:
            winreg.SetValueEx(key, "narrator", 0, winreg.REG_DWORD, 0)
            print("已设置 narrator = 0")
        
        print("讲述人已禁用，重启后不会自动启动。")
        
    except Exception as e:
        print(f"禁用讲述人失败: {e}")

if __name__ == "__main__":
    disable_narrator_on_startup()
    input("按Enter键退出...")