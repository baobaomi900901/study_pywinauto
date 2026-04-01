import threading
import sys
import time
import queue
import tkinter as tk
import uiautomation as auto
from pynput import mouse
import os

# ================== 全局控制 ==================
listener_running = True
inspect_mode = False
coord_queue = queue.Queue()
current_pid = os.getpid()

# ================== 持久高亮服务 ==================
highlight_queue = queue.Queue()
highlight_root = None
highlight_canvas = None
highlight_rect = None

def tkinter_worker():
    global highlight_root, highlight_canvas, highlight_rect
    highlight_root = tk.Tk()
    highlight_root.overrideredirect(True)
    highlight_root.attributes('-topmost', True)
    highlight_root.attributes('-transparentcolor', 'white')
    highlight_root.configure(bg='white')
    highlight_root.withdraw()
    highlight_canvas = tk.Canvas(highlight_root, highlightthickness=0, bg='white')
    highlight_canvas.pack()

    def update_highlight_from_queue():
        global highlight_root, highlight_canvas, highlight_rect
        try:
            while True:
                cmd = highlight_queue.get_nowait()
                if cmd['action'] == 'update':
                    x, y, w, h = cmd['x'], cmd['y'], cmd['width'], cmd['height']
                    highlight_root.withdraw()
                    highlight_root.geometry(f"{w}x{h}+{x}+{y}")
                    highlight_root.update_idletasks()
                    highlight_canvas.config(width=w, height=h)
                    highlight_canvas.delete("all")
                    highlight_rect = highlight_canvas.create_rectangle(
                        0, 0, w, h, outline='red', width=4, fill=''
                    )
                    highlight_root.after(10, lambda: highlight_root.deiconify())
                elif cmd['action'] == 'clear':
                    if highlight_rect:
                        highlight_canvas.delete(highlight_rect)
                        highlight_rect = None
                    highlight_root.withdraw()
        except queue.Empty:
            pass
        finally:
            highlight_root.after(30, update_highlight_from_queue)

    highlight_root.after(30, update_highlight_from_queue)
    highlight_root.mainloop()

def start_highlight_service():
    t = threading.Thread(target=tkinter_worker, daemon=True)
    t.start()

def update_highlight(x, y, width, height):
    highlight_queue.put({'action': 'clear'})
    highlight_queue.put({'action': 'update', 'x': x, 'y': y, 'width': width, 'height': height})

def clear_highlight():
    highlight_queue.put({'action': 'clear'})

# ================== 鼠标监听 ==================
def on_move(x, y):
    if inspect_mode:
        coord_queue.put((x, y))

def start_mouse_listener():
    with mouse.Listener(on_move=on_move) as listener:
        global listener_running
        while listener_running:
            listener.join(0.1)
        listener.stop()

# ================== 深度获取控件（忽略高亮窗口）==================
def is_highlight_window(ctrl):
    try:
        return ctrl.ClassName == "TkChild" and ctrl.ProcessId == current_pid
    except:
        return False

def get_deepest_control(x, y):
    """获取包含鼠标点的最深（面积最小）控件，忽略高亮窗口"""
    try:
        root = auto.ControlFromPoint(x, y)
        if not root:
            return None
        if is_highlight_window(root):
            return None
        from collections import deque
        queue = deque([root])
        candidates = []
        while queue:
            ctrl = queue.popleft()
            if is_highlight_window(ctrl):
                continue
            rect = ctrl.BoundingRectangle
            if rect and rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                candidates.append(ctrl)
            for child in ctrl.GetChildren():
                queue.append(child)
        if not candidates:
            return None
        candidates.sort(key=lambda c: (c.BoundingRectangle.width() * c.BoundingRectangle.height() 
                                      if c.BoundingRectangle else float('inf')))
        return candidates[0]
    except Exception as e:
        return None

# ================== UIA 工作线程 ==================
def uia_worker():
    print("[工作线程] 已启动，正在初始化 COM...")
    try:
        with auto.UIAutomationInitializerInThread():
            print("[工作线程] COM 初始化成功")
            global inspect_mode
            pending_coord = None
            last_move_time = 0
            last_processed_coord = None
            last_print_time = 0

            while listener_running:
                try:
                    x, y = coord_queue.get(timeout=0.1)
                    pending_coord = (x, y)
                    last_move_time = time.time()
                except queue.Empty:
                    pass

                if not inspect_mode:
                    pending_coord = None
                    last_move_time = 0
                    last_processed_coord = None
                    clear_highlight()
                    while not coord_queue.empty():
                        try:
                            coord_queue.get_nowait()
                        except queue.Empty:
                            break
                    time.sleep(0.1)
                    continue

                now = time.time()
                if (pending_coord is not None and
                    (now - last_move_time) >= 0.2 and
                    pending_coord != last_processed_coord):
                    x, y = pending_coord
                    try:
                        # 临时隐藏高亮窗口，避免遮挡
                        clear_highlight()
                        # 等待窗口隐藏（给高亮线程处理时间）
                        time.sleep(0.05)
                        
                        control = get_deepest_control(x, y)
                        if control:
                            rect = control.BoundingRectangle
                            if rect and rect.width() > 0 and rect.height() > 0:
                                x0, y0 = rect.left, rect.top
                                w = rect.width()
                                h = rect.height()
                                update_highlight(x0, y0, w, h)
                            else:
                                clear_highlight()
                            # 打印信息（限流）
                            if now - last_print_time > 0.1:
                                last_print_time = now
                                name = control.Name or ""
                                class_name = control.ClassName or ""
                                control_type = control.ControlTypeName or ""
                                automation_id = control.AutomationId or ""
                                ancestors = []
                                node = control
                                while node:
                                    node_name = node.Name if node.Name else node.ControlTypeName
                                    if node_name:
                                        ancestors.insert(0, node_name)
                                    node = node.GetParentControl()
                                hierarchy = " > ".join(ancestors)
                                pos_size = [rect.left, rect.top, rect.width(), rect.height()] if rect else [0,0,0,0]
                                print(f"\n[元素] 类型:{control_type} 名称:{name} 类名:{class_name} 自动化ID:{automation_id}")
                                print(f"鼠标坐标:({x},{y}) 位置尺寸:{pos_size}")
                                print(f"层级:{hierarchy}")
                            last_processed_coord = pending_coord
                        else:
                            # 没有找到有效控件，保持清除状态
                            clear_highlight()
                            last_processed_coord = pending_coord
                    except Exception as e:
                        print(f"[工作线程] 处理异常: {e}")
                        pending_coord = None
                        last_processed_coord = None
                time.sleep(0.05)
    except Exception as e:
        print(f"[工作线程] 初始化失败: {e}")

# ================== 主程序 ==================
def main():
    global listener_running, inspect_mode
    print("UI Auto Inspector 已启动")
    print("命令: start - 开始探测模式, stop - 停止探测, clear - 清除高亮, wq - 退出程序")
    print("提示: 鼠标停留 0.2 秒后高亮元素")

    start_highlight_service()

    uia_thread = threading.Thread(target=uia_worker, daemon=True)
    uia_thread.start()
    mouse_thread = threading.Thread(target=start_mouse_listener, daemon=True)
    mouse_thread.start()

    try:
        while True:
            user_input = input("\n>>> ").strip().lower()
            if user_input == "wq":
                print("正在退出...")
                listener_running = False
                break
            elif user_input == "start":
                if not inspect_mode:
                    inspect_mode = True
                    print("探测模式已开启，鼠标停留 0.2 秒后高亮元素")
                else:
                    print("探测模式已开启")
            elif user_input == "stop":
                if inspect_mode:
                    inspect_mode = False
                    clear_highlight()
                    print("探测模式已关闭")
                else:
                    print("探测模式未开启")
            elif user_input == "clear":
                clear_highlight()
                print("已清除当前高亮")
            else:
                print(f"未知命令: {user_input}")
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，退出")
    finally:
        listener_running = False
        mouse_thread.join(1)
        uia_thread.join(1)
        clear_highlight()
        print("程序已退出")

if __name__ == "__main__":
    main()