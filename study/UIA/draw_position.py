# 屏幕中绘制

import tkinter as tk

def show_red_rect(x: int, y: int, width: int, height: int, duration: float = 2.0):
    """
    在屏幕上绘制红色矩形框，并在终端中显示倒计时。
    :param x, y: 矩形左上角坐标（屏幕坐标）
    :param width, height: 矩形宽高
    :param duration: 显示时间（秒），默认2秒
    """
    root = tk.Tk()
    root.overrideredirect(True)               # 无边框
    root.attributes('-topmost', True)         # 置顶
    root.attributes('-transparentcolor', 'white')  # 白色透明
    root.configure(bg='white')
    root.geometry(f"{width}x{height}+{x}+{y}")

    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0, bg='white')
    canvas.pack()
    canvas.create_rectangle(0, 0, width, height, outline='red', width=10, fill='')

    remaining = duration

    def countdown():
        nonlocal remaining
        if remaining > 0:
            print(f"倒计时: {remaining:.1f} 秒", end='\r')
            remaining -= 0.1  # 更平滑的倒计时（每0.1秒更新一次）
            root.after(100, countdown)   # 每0.1秒更新一次
        else:
            print("倒计时结束", end='\n')
            root.destroy()

    countdown()
    root.mainloop()

# 示例用法
if __name__ == '__main__':
    show_red_rect(240, 533, 1090, 700)