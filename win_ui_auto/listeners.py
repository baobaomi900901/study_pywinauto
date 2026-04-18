# win_ui_auto/listeners.py
from pynput import mouse


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