# win_ui_auto/probe.py
import threading
import time
from constants import *
from highlight import HighlightWindow
from listeners import KeyboardListener, MouseMoveListener
from control_info import get_deepest_control, get_control_info, print_control_info, write_control_info_to_file


class UIProbe:
    def __init__(self):
        self.running = True
        self.inspect_mode = False
        self.current_control = None
        self.control_lock = threading.Lock()
        self.latest_coord = None
        self.coord_lock = threading.Lock()
        self.last_processed_coord = None
        self.last_printed_id = None
        self.last_print_time = 0
        self.print_interval = 0.1

        self.highlight = HighlightWindow()
        self.keyboard = KeyboardListener(on_f8=self._on_f8)
        self.mouse_move = MouseMoveListener(on_move=self._on_mouse_move)

    def _on_f8(self):
        if not self.inspect_mode:
            return
        print("[F8] 已按下，获取当前控件信息...")
        with self.control_lock:
            control = self.current_control
        if control:
            rect = control.BoundingRectangle
            if rect:
                x = rect.left + rect.width() // 2
                y = rect.top + rect.height() // 2
                info = get_control_info(control, x, y, self.highlight.get_pid())
                if info:
                    # 打印到控制台（带节流）
                    self.last_printed_id, self.last_print_time = print_control_info(
                        info, self.last_printed_id, self.last_print_time, self.print_interval
                    )
                    # 写入文件（总是写入，不受节流影响）
                    write_control_info_to_file(info)
                    print("→ 信息已打印")
                else:
                    print("→ 获取控件信息失败")
            else:
                print("→ 控件无边界矩形")
        else:
            print("→ 当前没有悬停控件，请先移动鼠标至目标控件并等待高亮")

    def _on_mouse_move(self, x, y):
        with self.coord_lock:
            self.latest_coord = (x, y)

    def _uia_worker(self):
        print("[UI探测] 线程启动...")
        try:
            import uiautomation as auto
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
                            self.highlight.clear()
                            with self.control_lock:
                                self.current_control = None
                        time.sleep(NON_INSPECT_SLEEP)
                        continue

                    now = time.time()
                    if (pending_coord is not None and
                            (now - last_move_time) >= HOVER_DELAY and
                            pending_coord != self.last_processed_coord):
                        x, y = pending_coord
                        try:
                            self.highlight.clear()
                            time.sleep(CLEAR_DELAY)
                            control = get_deepest_control(x, y, self.highlight.get_pid())
                            if control:
                                rect = control.BoundingRectangle
                                if rect and rect.width() > 0 and rect.height() > 0:
                                    self.highlight.update(rect.left, rect.top, rect.width(), rect.height())
                                with self.control_lock:
                                    self.current_control = control
                                self.last_processed_coord = pending_coord
                            else:
                                self.highlight.clear()
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

    def run(self):
        print("UI 探测工具（按F8打印当前高亮控件信息，无需管理员权限）")
        print("命令: 1 - 开启探查模式, 2 - 关闭, clear - 清除高亮, wq - 退出")
        print("使用方法：")
        print(" • 开启后，鼠标悬停 0.8 秒 → 红色高亮框")
        print(" • 按 F8 键 → 打印当前高亮控件的完整信息（包括父级链）")

        time.sleep(0.5)  # 等待高亮窗口初始化

        self.keyboard.start()
        self.mouse_move.start()

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
                    self.highlight.clear()
                    with self.control_lock:
                        self.current_control = None
                    print("探查模式已关闭")
                elif user_input == "clear":
                    self.highlight.clear()
                    with self.control_lock:
                        self.current_control = None
                    print("已清除高亮")
                else:
                    print("未知命令")
        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            self.running = False
            self.highlight.stop()
            self.keyboard.stop()
            self.mouse_move.stop()
            uia_thread.join(2)
            print("程序已退出")