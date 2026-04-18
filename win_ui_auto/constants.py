# win_ui_auto/constants.py
HOVER_DELAY = 0.8          # 悬停延迟（秒）
CLEAR_DELAY = 0.05         # 清除高亮后的短暂延迟
QUEUE_TIMEOUT = 0.1        # 队列超时
LOOP_SLEEP = 0.03          # UI探测循环睡眠时间
NON_INSPECT_SLEEP = 0.1    # 非探查模式下的睡眠时间
DEBUG = True              # 调试输出开关

# 探查模式：鼠标静止超过该秒数自动退出
INSPECT_MOUSE_IDLE_TIMEOUT_SECONDS = 10.0

# 高亮框扩展像素：防止边缘点击命中不稳
HIGHLIGHT_PADDING_PX = 2

# 与本工具窗口一致，供启动时清理残留（须与 capture_overlay / highlight 同步）
CAPTURE_OVERLAY_CLASS = "WinUiAuto_CaptureOverlay"
# Tk 顶层标题：用于 EnumWindows 识别探查红框（类名多为 TkTopLevel）
HIGHLIGHT_TOPLEVEL_TITLE = "WinUiAuto_HighlightOverlay"