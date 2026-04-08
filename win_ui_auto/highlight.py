# highlight.py
import threading
import queue
import tkinter as tk

class HighlightWindow:
    def __init__(self):
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.root = None
        self.canvas = None
        self.rect = None
        self.pid = None
        self.thread.start()

    def _run(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', 'white')
        self.root.configure(bg='white')
        self.root.withdraw()

        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg='white')
        self.canvas.pack()

        # 获取高亮窗口的PID（用于过滤）
        try:
            hwnd = self.root.winfo_id()
            import ctypes
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            self.pid = pid.value
        except:
            import os
            self.pid = os.getpid()

        def process_queue():
            try:
                while True:
                    cmd = self.queue.get_nowait()
                    if cmd['action'] == 'update':
                        x, y, w, h = cmd['x'], cmd['y'], cmd['width'], cmd['height']
                        self.root.geometry(f"{w}x{h}+{x}+{y}")
                        self.canvas.config(width=w, height=h)
                        if self.rect:
                            self.canvas.coords(self.rect, 0, 0, w, h)
                        else:
                            self.rect = self.canvas.create_rectangle(
                                0, 0, w, h, outline='red', width=4, fill=''
                            )
                        self.root.deiconify()
                    elif cmd['action'] == 'clear':
                        if self.rect:
                            self.canvas.delete(self.rect)
                            self.rect = None
                        self.root.withdraw()
                    elif cmd['action'] == 'quit':
                        self.root.quit()
                        return
            except queue.Empty:
                pass
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
        # 等待pid获取完成
        while self.pid is None:
            import time
            time.sleep(0.01)
        return self.pid