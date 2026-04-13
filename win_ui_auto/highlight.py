# win_ui_auto/highlight.py
import threading
import queue
import tkinter as tk
import time


class HighlightWindow:
    def __init__(self):
        self.queue = queue.Queue()
        self.root = None
        self.canvas = None
        self.rect = None
        self.pid = None
        # 使用 Event 确保 pid 被正确获取后再返回给外层
        self.ready_event = threading.Event()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        # 阻塞等待窗口初始化完成，确保外层调用 update 时窗口已就绪
        self.ready_event.wait(timeout=2)

    def _run(self):
        self.root = tk.Tk()
        # 基础设置：无边框、置顶、透明色
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', 'white')
        self.root.configure(bg='white')
        self.root.withdraw()

        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg='white')
        self.canvas.pack(fill='both', expand=True)

        # 稳定性获取 PID
        try:
            self.root.update_idletasks()  # 强制刷新以获取真实 window id
            hwnd = self.root.winfo_id()
            import ctypes
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            self.pid = pid.value
        except:
            import os
            self.pid = os.getpid()

        self.ready_event.set()

        def process_queue():
            try:
                while True:
                    cmd = self.queue.get_nowait()
                    if cmd['action'] == 'update':
                        x, y, w, h = cmd['x'], cmd['y'], cmd['width'], cmd['height']
                        # 增加一层保护，防止宽高为0导致 Tkinter 报错
                        w = max(w, 1)
                        h = max(h, 1)

                        self.root.geometry(f"{w}x{h}+{x}+{y}")
                        self.canvas.config(width=w, height=h)

                        if self.rect:
                            self.canvas.coords(self.rect, 0, 0, w, h)
                        else:
                            self.rect = self.canvas.create_rectangle(
                                0, 0, w, h, outline='red', width=4, fill=''
                            )
                        self.root.deiconify()
                        self.root.lift()  # 确保在倒计时期间始终处于最前方

                    elif cmd['action'] == 'clear':
                        if self.rect:
                            self.canvas.delete(self.rect)
                            self.rect = None
                        self.root.withdraw()

                    elif cmd['action'] == 'quit':
                        self.root.destroy()
                        return
            except queue.Empty:
                pass
            # 保持 30ms 刷新率，兼顾性能与响应速度
            self.root.after(30, process_queue)

        self.root.after(30, process_queue)
        self.root.mainloop()

    def update(self, x, y, width, height):
        self.queue.put({'action': 'update', 'x': x, 'y': y, 'width': width, 'height': height})

    def clear(self):
        self.queue.put({'action': 'clear'})

    def stop(self):
        self.queue.put({'action': 'quit'})

    def get_pid(self):
        return self.pid