import os
import sys
import psutil
import subprocess
import time

TARGET_APP = "iDeal.exe"


def inject_and_restart():
    print("=" * 50)
    print("🚀 Chromium 强制注入启动器")
    print("=" * 50)

    app_path = None

    # 1. 寻找正在运行的进程，获取它的绝对路径
    print(f"[*] 正在扫描运行中的 {TARGET_APP}...")
    for proc in psutil.process_iter(['name', 'exe']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == TARGET_APP.lower():
                app_path = proc.info['exe']
                print(f"[+] 提取到物理路径: {app_path}")
                print("[*] 正在强行结束原进程以准备注入...")
                proc.kill()
                proc.wait(timeout=3)
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    # 2. 如果应用没在运行，让用户手动输入路径
    if not app_path:
        print(f"[!] 未在后台发现 {TARGET_APP}。")
        app_path = input("请输入 iDeal.exe 的完整快捷方式路径 (如 C:\\xxx\\iDeal.exe):\n>>> ").strip()
        app_path = app_path.strip('"').strip("'")

    if not os.path.exists(app_path):
        print("[-] 路径无效或文件不存在，注入中止。")
        return

    time.sleep(1)  # 给系统一点时间清理进程

    # 3. 构造魔法参数
    cmd = [
        app_path,
        "--force-renderer-accessibility",  # 强开 UIA 树
        "--remote-debugging-port=9222"     # 强开 Web 调试后门
    ]

    print("\n[*] 正在执行底层参数注入...")
    print(f"[*] 注入指令: {' '.join(cmd)}")

    # 4. 启动应用
    try:
        # 使用 Popen 让它在后台独立运行，不阻塞当前的 Python 脚本
        subprocess.Popen(cmd)
        print("\n[+] 🟢 注入启动成功！")
    except Exception as e:
        print(f"[-] ❌ 启动失败: {e}")
        return


if __name__ == "__main__":
    inject_and_restart()