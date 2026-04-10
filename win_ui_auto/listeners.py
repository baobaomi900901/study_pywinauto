# win_ui_auto/listeners.py
from pynput import keyboard, mouse

class KeyboardListener:
    def __init__(self, on_f8):
        self.on_f8 = on_f8
        self.listener = None

    def _on_press(self, key):
        try:
            if key == keyboard.Key.f8:
                self.on_f8()
        except:
            pass

    def start(self):
        self.listener = keyboard.Listener(on_press=self._on_press)
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