# win_ui_auto_f8.py - 仅探查，F8打印控件信息，无需管理员权限
import threading
import time
import queue
import tkinter as tk
import uiautomation as auto
from pynput import keyboard, mouse
import json
import os
import ctypes

# ==================== 配置常量 ====================
HOVER_DELAY = 0.8
CLEAR_DELAY = 0.05
QUEUE_TIMEOUT = 0.1
LOOP_SLEEP = 0.03
NON_INSPECT_SLEEP = 0.1
DEBUG = False                 # 关闭调试输出

# ==================== 进程名获取（用于 application 信息） ====================
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MAX_PATH = 260

kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

def get_process_name(pid):
    # 根据进程 ID（PID）获取该进程的可执行文件名
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


class UIProbe:
    def __init__(self):
        self.running = True
        self.inspect_mode = False
        self.latest_coord = None
        self.coord_lock = threading.Lock()
        self.current_control = None          # 悬停时存储的控件
        self.control_lock = threading.Lock()
        self.highlight_queue = queue.Queue()
        self.current_pid = None
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
        # 获取高亮窗口的进程ID，用于过滤
        try:
            hwnd = self.highlight_root.winfo_id()
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            self.current_pid = pid.value
        except:
            self.current_pid = os.getpid()

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
        while self.current_pid is None:
            time.sleep(0.05)

    def update_highlight(self, x, y, width, height):
        self.highlight_queue.put({'action': 'update', 'x': x, 'y': y, 'width': width, 'height': height})

    def clear_highlight(self):
        self.highlight_queue.put({'action': 'clear'})

    def stop_highlight_service(self):
        self.highlight_queue.put({'action': 'quit'})

    # ------------------- 键盘监听（F8） -------------------
    def _on_press(self, key):
        try:
            # 检测 F8 键
            if key == keyboard.Key.f8:
                if not self.inspect_mode:
                    return
                print("[F8] 已按下，获取当前控件信息...")
                with self.control_lock:
                    control = self.current_control
                if control:
                    # 获取控件中心点坐标用于信息采集（也可直接用鼠标坐标，但 current_control 已经是最深控件）
                    rect = control.BoundingRectangle
                    if rect:
                        x = rect.left + rect.width() // 2
                        y = rect.top + rect.height() // 2
                        info = self._get_control_info(control, x, y)
                        if info:
                            self._print_control_info(info)
                            print("→ 信息已打印")
                        else:
                            print("→ 获取控件信息失败")
                    else:
                        print("→ 控件无边界矩形")
                else:
                    print("→ 当前没有悬停控件，请先移动鼠标至目标控件并等待高亮")
        except Exception as e:
            print(f"[键盘] 异常: {e}")

    def _on_release(self, key):
        pass  # 不需要处理释放

    # ------------------- 鼠标移动监听（悬停）-------------------
    def _on_move(self, x, y):
        with self.coord_lock:
            self.latest_coord = (x, y)

    # ------------------- UI 探测辅助函数 -------------------
    def _is_highlight_window(self, ctrl):
        try:
            return (ctrl.ClassName == "TkChild" and ctrl.ProcessId == self.current_pid)
        except:
            return False

    def _is_same_control(self, ctrl1, ctrl2):
        if ctrl1 is None or ctrl2 is None:
            return False
        try:
            if ctrl1.AutomationId and ctrl2.AutomationId:
                return ctrl1.AutomationId == ctrl2.AutomationId
            if (ctrl1.ControlTypeName == ctrl2.ControlTypeName and
                ctrl1.ClassName == ctrl2.ClassName and ctrl1.Name == ctrl2.Name):
                r1 = ctrl1.BoundingRectangle
                r2 = ctrl2.BoundingRectangle
                if r1 and r2:
                    return (r1.left == r2.left and r1.top == r2.top and
                            r1.width() == r2.width() and r1.height() == r2.height())
            return False
        except:
            return ctrl1 == ctrl2

    def _get_deepest_control(self, x, y):
        try:
            ctrl = auto.ControlFromPoint(x, y)
            if not ctrl or self._is_highlight_window(ctrl):
                return None
            while True:
                children = ctrl.GetChildren()
                found_deeper = False
                for child in children:
                    if self._is_highlight_window(child):
                        continue
                    rect = child.BoundingRectangle
                    if rect and rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                        ctrl = child
                        found_deeper = True
                        break
                if not found_deeper:
                    break
            return ctrl
        except Exception:
            return None

    def _get_control_info(self, control, x, y):
        try:
            rect = control.BoundingRectangle
            if not rect:
                return None
            x0, y0, w, h = rect.left, rect.top, rect.width(), rect.height()

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
                is_password = getattr(control, 'IsPassword', False)
            except:
                is_password = False

            ctrl_type = control.ControlTypeName or ""

            my_index = 0
            my_same_type_index = 0
            try:
                my_parent = control.GetParentControl()
                if my_parent:
                    siblings = my_parent.GetChildren()
                    same_type_count = 0
                    for i, sibling in enumerate(siblings):
                        if self._is_same_control(sibling, control):
                            my_index = i
                        if sibling.ControlTypeName == ctrl_type:
                            if self._is_same_control(sibling, control):
                                my_same_type_index = same_type_count
                            same_type_count += 1
            except:
                pass

            parent_chain = []
            app_info = None
            node = control.GetParentControl()
            while node and not self._is_highlight_window(node):
                node_type = node.ControlTypeName or ""
                node_index = 0
                node_same_type_index = 0
                try:
                    grandparent = node.GetParentControl()
                    if grandparent:
                        siblings = grandparent.GetChildren()
                        same_type_count = 0
                        for i, sibling in enumerate(siblings):
                            if self._is_same_control(sibling, node):
                                node_index = i
                            if sibling.ControlTypeName == node_type:
                                if self._is_same_control(sibling, node):
                                    node_same_type_index = same_type_count
                                same_type_count += 1
                except:
                    pass

                node_info = {
                    "ControlType": node_type,
                    "ClassName": node.ClassName or "",
                    "index": node_index,
                    "same_type_index": node_same_type_index
                }
                if node_type == "PaneControl" and node.ClassName == "#32769":
                    node_info["is_desktop"] = True
                if node_type == "WindowControl" and app_info is None:
                    node_info["is_app"] = True
                    pid = node.ProcessId
                    if pid:
                        process_name = get_process_name(pid)
                        app_info = {"pid": pid, "name": process_name or "未知"}
                parent_chain.insert(0, node_info)
                node = node.GetParentControl()

            info = {
                "ControlType": ctrl_type,
                "ClassName": control.ClassName or "",
                "Name": control.Name or "",
                "position": [x0, y0, w, h],
                "Value": value,
                "HelpText": help_text,
                "IsPassword": is_password,
                "index": my_index,
                "same_type_index": my_same_type_index,
                "parent": parent_chain
            }
            if app_info:
                info["application"] = app_info
            return info
        except Exception:
            return None

    def _print_control_info(self, info):
        if not info:
            return
        pos = info["position"]
        ctrl_id = (info["ControlType"], info["ClassName"], info["Name"],
                   info.get("index"), info.get("same_type_index"),
                   round(pos[0] / 5) * 5, round(pos[1] / 5) * 5)
        now = time.time()
        if ctrl_id != self.last_printed_control_id or now - self.last_print_time > self.print_interval:
            print(f"\n[UI 信息]\n{json.dumps(info, ensure_ascii=False, indent=2)}")
            self.last_printed_control_id = ctrl_id
            self.last_print_time = now

    # ------------------- UI 探测工作线程 -------------------
    def _uia_worker(self):
        print("[UI探测] 线程启动...")
        try:
            with auto.UIAutomationInitializerInThread():
                print("[UI探测] COM初始化成功")
                pending_coord = None
                last_move_time = 0
                while self.running:
                    with self.coord_lock:
                        coord = self.latest_coord
                        self.latest_coord = None
                    if coord is not None:
                        pending_coord = coord
                        last_move_time = time.time()

                    if not self.inspect_mode:
                        if pending_coord is not None:
                            pending_coord = None
                            self.clear_highlight()
                            with self.control_lock:
                                self.current_control = None
                        time.sleep(NON_INSPECT_SLEEP)
                        continue

                    now = time.time()
                    if (pending_coord is not None and
                            (now - last_move_time) >= HOVER_DELAY and
                            pending_coord != getattr(self, 'last_processed_coord', None)):
                        x, y = pending_coord
                        try:
                            self.clear_highlight()
                            time.sleep(CLEAR_DELAY)
                            control = self._get_deepest_control(x, y)
                            if control:
                                rect = control.BoundingRectangle
                                if rect and rect.width() > 0 and rect.height() > 0:
                                    self.update_highlight(rect.left, rect.top, rect.width(), rect.height())
                                with self.control_lock:
                                    self.current_control = control
                                self.last_processed_coord = pending_coord
                            else:
                                self.clear_highlight()
                                with self.control_lock:
                                    self.current_control = None
                                self.last_processed_coord = pending_coord
                        except Exception as e:
                            if DEBUG:
                                print(f"[DEBUG] UI探测处理异常: {e}")
                            pending_coord = None
                            with self.control_lock:
                                self.current_control = None
                    time.sleep(LOOP_SLEEP)
        except Exception as e:
            print(f"[UI探测] 初始化失败: {e}")
        finally:
            print("[UI探测] 线程退出")

    # ------------------- 主程序 -------------------
    def run(self):
        print("UI 探测工具（按F8打印当前高亮控件信息，无需管理员权限）")
        print("命令: 1 - 开启探查模式, 2 - 关闭, clear - 清除高亮, wq - 退出")
        print("使用方法：")
        print(" • 开启后，鼠标悬停 0.8 秒 → 红色高亮框")
        print(" • 按 F8 键 → 打印当前高亮控件的完整信息（包括父级链）")

        self.start_highlight_service()

        # 启动键盘监听（监听F8）
        kb_listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        # 启动鼠标移动监听（用于悬停）
        mouse_move_listener = mouse.Listener(on_move=self._on_move)

        kb_listener.start()
        mouse_move_listener.start()

        # UI探测线程
        uia_thread = threading.Thread(target=self._uia_worker, daemon=True)
        uia_thread.start()

        try:
            while self.running:
                user_input = input("\n>>> ").strip().lower()
                if user_input == "wq":
                    print("正在退出...")
                    self.running = False
                    break
                elif user_input == "1":
                    self.inspect_mode = True
                    print("探查模式已开启 → 移动鼠标至目标控件，等待高亮后按F8打印信息")
                elif user_input == "2":
                    self.inspect_mode = False
                    self.clear_highlight()
                    with self.control_lock:
                        self.current_control = None
                    print("探查模式已关闭")
                elif user_input == "clear":
                    self.clear_highlight()
                    with self.control_lock:
                        self.current_control = None
                    print("已清除高亮")
                else:
                    print("未知命令")
        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            self.running = False
            self.stop_highlight_service()
            kb_listener.stop()
            mouse_move_listener.stop()
            uia_thread.join(2)
            print("程序已退出")

if __name__ == "__main__":
    probe = UIProbe()
    probe.run()