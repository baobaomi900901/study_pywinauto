# win_ui_auto/listeners.py
from pynput import keyboard, mouse

class KeyboardListener:
    """
    只负责记录 Ctrl 键是否按下（供 Ctrl+鼠标左键触发抓取使用）。
    """
    def __init__(self):
        self.ctrl_down = False
        self.listener = None

    def _is_ctrl(self, key):
        return key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

    def _on_press(self, key):
        try:
            if self._is_ctrl(key):
                self.ctrl_down = True
        except:
            pass

    def _on_release(self, key):
        try:
            if self._is_ctrl(key):
                self.ctrl_down = False
        except:
            pass

    def start(self):
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()

class MouseMoveListener:
    def __init__(self, on_move):
        self.on_move = on_move
        self.listener = None

    def _on_move(self, x, y):
        self.on_move(x, y)

    def start(self):
        self.listener = mouse.Listener(on_move=self._on_move)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()


class CtrlClickListener:
    """
    监听鼠标左键点击；当 Ctrl 按下时触发回调。
    """
    def __init__(self, is_ctrl_down, on_trigger):
        self.is_ctrl_down = is_ctrl_down
        self.on_trigger = on_trigger
        self.listener = None

    def _on_click(self, x, y, button, pressed):
        try:
            if not pressed:
                return
            if button != mouse.Button.left:
                return
            if self.is_ctrl_down():
                self.on_trigger()
        except:
            pass

    def start(self):
        self.listener = mouse.Listener(on_click=self._on_click)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()