# ui_auto.py
import threading
import sys
import time
import queue
import tkinter as tk
import uiautomation as auto
from pynput import mouse
import os
import json
from collections import deque
import ctypes
import ctypes.wintypes

# ==================== 配置常量 ====================
HOVER_DELAY = 1
CLEAR_DELAY = 0.05
QUEUE_TIMEOUT = 0.1
LOOP_SLEEP = 0.05
NON_INSPECT_SLEEP = 0.1
DEBUG = False

# ==================== Windows API 相关 ====================
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MAX_PATH = 260

kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi


def get_process_name(pid):
    """通过 PID 获取进程名称（exe 文件名）"""
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            return None
        try:
            name_buffer = ctypes.create_unicode_buffer(MAX_PATH)
            size = ctypes.c_uint(MAX_PATH)
            if psapi.GetModuleBaseNameW(handle, None, name_buffer, size):
                return name_buffer.value
            if psapi.GetProcessImageFileNameW(handle, name_buffer, size):
                full_path = name_buffer.value
                return full_path.split('\\')[-1] if '\\' in full_path else full_path
            return None
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


class UIExplorer:
    def __init__(self):
        self.listener_running = True
        self.inspect_mode = False
        self.stop_event = threading.Event()
        self.latest_coord = None
        self.coord_lock = threading.Lock()
        self.last_processed_coord = None
        self.highlight_queue = queue.Queue()
        self.current_pid = os.getpid()
        self.last_printed_control_id = None
        self.last_print_time = 0
        self.print_interval = 0.1
        self.highlight_root = None
        self.highlight_canvas = None
        self.highlight_rect = None

    # ------------------- 高亮窗口线程 -------------------
    def _tkinter_worker(self):
        self.highlight_root = tk.Tk()
        self.highlight_root.overrideredirect(True)
        self.highlight_root.attributes('-topmost', True)
        self.highlight_root.attributes('-transparentcolor', 'white')
        self.highlight_root.configure(bg='white')
        self.highlight_root.withdraw()
        self.highlight_canvas = tk.Canvas(self.highlight_root, highlightthickness=0, bg='white')
        self.highlight_canvas.pack()

        def update_highlight_from_queue():
            try:
                while True:
                    cmd = self.highlight_queue.get_nowait()
                    if cmd['action'] == 'update':
                        x, y, w, h = cmd['x'], cmd['y'], cmd['width'], cmd['height']
                        self.highlight_root.geometry(f"{w}x{h}+{x}+{y}")
                        self.highlight_canvas.config(width=w, height=h)
                        if self.highlight_rect:
                            self.highlight_canvas.coords(self.highlight_rect, 0, 0, w, h)
                        else:
                            self.highlight_rect = self.highlight_canvas.create_rectangle(
                                0, 0, w, h, outline='red', width=4, fill=''
                            )
                        self.highlight_root.deiconify()
                    elif cmd['action'] == 'clear':
                        if self.highlight_rect:
                            self.highlight_canvas.delete(self.highlight_rect)
                            self.highlight_rect = None
                        self.highlight_root.withdraw()
                    elif cmd['action'] == 'quit':
                        self.highlight_root.quit()
                        return
            except queue.Empty:
                pass
            self.highlight_root.after(30, update_highlight_from_queue)

        self.highlight_root.after(30, update_highlight_from_queue)
        self.highlight_root.mainloop()

    def start_highlight_service(self):
        t = threading.Thread(target=self._tkinter_worker, daemon=True)
        t.start()

    def update_highlight(self, x, y, width, height):
        self.highlight_queue.put({'action': 'update', 'x': x, 'y': y, 'width': width, 'height': height})

    def clear_highlight(self):
        self.highlight_queue.put({'action': 'clear'})

    def stop_highlight_service(self):
        self.highlight_queue.put({'action': 'quit'})

    # ------------------- 鼠标监听线程 -------------------
    def _on_move(self, x, y):
        if self.inspect_mode:
            with self.coord_lock:
                self.latest_coord = (x, y)

    def _mouse_listener_worker(self):
        with mouse.Listener(on_move=self._on_move) as listener:
            while not self.stop_event.is_set():
                listener.join(QUEUE_TIMEOUT)
            listener.stop()
            if DEBUG:
                print("[鼠标] 监听线程已停止")

    # ------------------- UI 探测辅助函数 -------------------
    def _is_highlight_window(self, ctrl):
        try:
            return (ctrl.ClassName == "TkChild" and ctrl.ProcessId == self.current_pid)
        except:
            return False

    def _get_deepest_control(self, x, y):
        try:
            root = auto.ControlFromPoint(x, y)
            if not root:
                return None
            if self._is_highlight_window(root):
                return None

            queue = deque([root])
            candidates = []
            while queue:
                ctrl = queue.popleft()
                if self._is_highlight_window(ctrl):
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
            if DEBUG:
                print(f"[DEBUG] _get_deepest_control 异常: {e}")
            return None

    def _get_control_info(self, control, x, y):
        """提取控件详细信息，为目标控件和所有父级添加正确的 index 字段"""
        try:
            rect = control.BoundingRectangle
            if not rect:
                return None

            x0, y0, w, h = rect.left, rect.top, rect.width(), rect.height()

            # 获取 Value、HelpText、IsPassword
            try:
                value_pattern = control.GetValuePattern()
                value = value_pattern.Value if value_pattern else ""
            except:
                value = ""

            try:
                help_text = control.HelpText or ""
            except:
                help_text = ""

            try:
                is_password = control.IsPassword if hasattr(control, 'IsPassword') else False
            except:
                is_password = False

            # ==================== 计算目标控件自身的 index ====================
            my_index = 0
            try:
                my_parent = control.GetParentControl()
                if my_parent:
                    siblings = my_parent.GetChildren()
                    for i, sibling in enumerate(siblings):
                        if self._is_same_control(sibling, control):
                            my_index = i
                            break
            except Exception:
                my_index = 0

            # ==================== 收集父级链 + 每个父级的 index ====================
            parent_chain = []
            app_info = None

            node = control.GetParentControl()
            while node and not self._is_highlight_window(node):
                # 计算当前 node 在其父控件中的 index
                node_index = 0
                try:
                    grandparent = node.GetParentControl()
                    if grandparent:
                        siblings = grandparent.GetChildren()
                        for i, sibling in enumerate(siblings):
                            if self._is_same_control(sibling, node):
                                node_index = i
                                break
                except Exception:
                    node_index = 0

                node_info = {
                    "ControlType": node.ControlTypeName or "",
                    "ClassName": node.ClassName or "",
                    "index": node_index
                }

                # 特殊标记
                if (node.ControlTypeName == "PaneControl" and node.ClassName == "#32769"):
                    node_info["is_desktop"] = True

                if node.ControlTypeName == "WindowControl" and app_info is None:
                    node_info["is_app"] = True
                    pid = node.ProcessId
                    if pid:
                        process_name = get_process_name(pid)
                        app_info = {
                            "pid": pid,
                            "name": process_name or "未知"
                        }

                parent_chain.insert(0, node_info)
                node = node.GetParentControl()

            # ==================== 构建返回信息 ====================
            info = {
                "ControlType": control.ControlTypeName or "",
                "ClassName": control.ClassName or "",
                "Name": control.Name or "",
                "position": [x0, y0, w, h],
                "Value": value,
                "HelpText": help_text,
                "IsPassword": is_password,
                "index": my_index,
                "parent": parent_chain
            }

            if app_info:
                info["application"] = app_info

            return info

        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] _get_control_info 异常: {e}")
            return None

    # 新增辅助函数：更可靠地判断两个控件是否为同一个
    def _is_same_control(self, ctrl1, ctrl2):
        """判断两个 uiautomation 控件是否指向同一个 UI 元素"""
        if ctrl1 is None or ctrl2 is None:
            return False
        try:
            # 优先使用 AutomationId（最可靠）
            if ctrl1.AutomationId and ctrl2.AutomationId:
                if ctrl1.AutomationId == ctrl2.AutomationId:
                    return True

            # 备用方案：类型 + ClassName + Name + 位置大小
            if (ctrl1.ControlTypeName == ctrl2.ControlTypeName and
                ctrl1.ClassName == ctrl2.ClassName and
                ctrl1.Name == ctrl2.Name):

                r1 = ctrl1.BoundingRectangle
                r2 = ctrl2.BoundingRectangle
                if r1 and r2:
                    return (r1.left == r2.left and r1.top == r2.top and
                            r1.width() == r2.width() and r1.height() == r2.height())
            return False
        except:
            # 最保守的兜底：直接比较对象引用
            return ctrl1 == ctrl2

    def _print_control_info(self, info):
        if not info:
            return
        # 使用更稳定的标识符来避免频繁重复打印
        ctrl_id = (info["ControlType"], info["ClassName"], info["Name"],
                   info.get("index"), info["position"][0], info["position"][1])
        now = time.time()
        if ctrl_id != self.last_printed_control_id or now - self.last_print_time > self.print_interval:
            print(f"\n[UI 信息]\n{json.dumps(info, ensure_ascii=False, indent=2)}")
            self.last_printed_control_id = ctrl_id
            self.last_print_time = now

    # ------------------- UI 探测工作线程 -------------------
    def _uia_worker(self):
        print("[UI探测] 线程启动，初始化COM...")
        try:
            with auto.UIAutomationInitializerInThread():
                print("[UI探测] COM初始化成功")
                last_move_time = 0
                pending_coord = None
                while not self.stop_event.is_set():
                    with self.coord_lock:
                        coord = self.latest_coord
                        self.latest_coord = None

                    if coord is not None:
                        pending_coord = coord
                        last_move_time = time.time()

                    if not self.inspect_mode:
                        if pending_coord is not None:
                            pending_coord = None
                            self.last_processed_coord = None
                            self.clear_highlight()
                        time.sleep(NON_INSPECT_SLEEP)
                        continue

                    now = time.time()
                    if (pending_coord is not None and
                            (now - last_move_time) >= HOVER_DELAY and
                            pending_coord != self.last_processed_coord):

                        x, y = pending_coord
                        try:
                            self.clear_highlight()
                            time.sleep(CLEAR_DELAY)

                            control = self._get_deepest_control(x, y)
                            if control:
                                rect = control.BoundingRectangle
                                if rect and rect.width() > 0 and rect.height() > 0:
                                    self.update_highlight(rect.left, rect.top, rect.width(), rect.height())
                                else:
                                    self.clear_highlight()

                                info = self._get_control_info(control, x, y)
                                if info:
                                    self._print_control_info(info)

                                self.last_processed_coord = pending_coord
                            else:
                                self.clear_highlight()
                                self.last_processed_coord = pending_coord
                        except Exception as e:
                            if DEBUG:
                                print(f"[DEBUG] UI探测处理异常: {e}")
                            pending_coord = None
                            self.last_processed_coord = None

                    time.sleep(LOOP_SLEEP)
        except Exception as e:
            print(f"[UI探测] 初始化失败: {e}")
        finally:
            print("[UI探测] 线程退出")

    # ------------------- 主程序入口 -------------------
    def run(self):
        print("UI 自动探查器已启动")
        print(f"命令: 1 - 开启探查模式, 2 - 关闭探查模式, clear - 清除高亮, wq - 退出程序")
        print(f"提示: 鼠标在控件上停留 {HOVER_DELAY} 秒后，会高亮显示该控件并打印信息")
        self.start_highlight_service()

        uia_thread = threading.Thread(target=self._uia_worker, daemon=True)
        uia_thread.start()
        mouse_thread = threading.Thread(target=self._mouse_listener_worker, daemon=True)
        mouse_thread.start()

        try:
            while self.listener_running:
                user_input = input("\n>>> ").strip().lower()
                if user_input == "wq":
                    print("正在退出程序...")
                    self.listener_running = False
                    self.stop_event.set()
                    break
                elif user_input == "1":
                    if not self.inspect_mode:
                        self.inspect_mode = True
                        print(f"探查模式已开启，鼠标停留 {HOVER_DELAY} 秒后高亮元素")
                    else:
                        print("探查模式已开启")
                elif user_input == "2":
                    if self.inspect_mode:
                        self.inspect_mode = False
                        self.clear_highlight()
                        print("探查模式已关闭")
                    else:
                        print("探查模式未开启")
                elif user_input == "clear":
                    self.clear_highlight()
                    print("已清除当前高亮")
                else:
                    print(f"未知命令: {user_input}")
        except KeyboardInterrupt:
            print("\n检测到 Ctrl+C，退出程序")
        finally:
            self.listener_running = False
            self.stop_event.set()
            self.stop_highlight_service()
            mouse_thread.join(2)
            uia_thread.join(2)
            time.sleep(0.1)
            print("程序已退出")


if __name__ == "__main__":
    explorer = UIExplorer()
    explorer.run()