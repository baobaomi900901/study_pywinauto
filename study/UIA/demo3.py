# ui_inspector.py
# UIAutomation 控件树 → XML/XPath 查询 + 屏幕高亮
#
# 依赖: pip install uiautomation lxml
#
# 用法速览:
#   tree = build_tree(auto.WindowControl(Name="记事本"))
#   nodes = tree.xpath('//EditControl[@IsEnabled="True"]')
#   highlight_nodes(nodes, color="lime", duration=3.0)

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from typing import Optional, Union

try:
    import uiautomation as auto
except ImportError:
    auto = None  # type: ignore

try:
    from lxml import etree
except ImportError:
    etree = None  # type: ignore


# ══════════════════════════════════════════════════════════════════════════════
# 1. 控件树序列化
# ══════════════════════════════════════════════════════════════════════════════

def build_tree(control, parent=None, *, max_depth: int = 32, _depth: int = 0):
    """
    将 UIAutomation 控件树序列化为 lxml ElementTree。
    BoundingRectangle 被写成 x/y/width/height 属性，可直接用于高亮。

    :param control:   uiautomation 控件对象（任意类型均可）
    :param parent:    内部递归用，外部调用不需要传
    :param max_depth: 最大递归深度，防止超深控件树卡死
    :return: lxml Element（根节点时）或 None（超深跳过）
    """
    if _depth > max_depth:
        return None

    tag = (control.ControlTypeName or "Unknown").replace(" ", "")
    rect = control.BoundingRectangle

    attrs = {
        "Name":         control.Name or "",
        "AutomationId": control.AutomationId or "",
        "ClassName":    control.ClassName or "",
        "ControlType":  control.ControlTypeName or "",
        "IsEnabled":    str(control.IsEnabled),
        "IsOffscreen":  str(control.IsOffscreen),
        "x":            str(rect.left),
        "y":            str(rect.top),
        "width":        str(rect.width()),
        "height":       str(rect.height()),
    }

    elem = (
        etree.SubElement(parent, tag, attrs)
        if parent is not None
        else etree.Element(tag, attrs)
    )

    for child in control.GetChildren():
        build_tree(child, elem, max_depth=max_depth, _depth=_depth + 1)

    return elem


def dump_xml(control, path: str = "ui_tree.xml", *, pretty: bool = True):
    """序列化后写入文件，方便调试时浏览完整控件树。"""
    root = build_tree(control)
    tree = etree.ElementTree(root)
    with open(path, "wb") as f:
        tree.write(f, pretty_print=pretty, xml_declaration=True, encoding="utf-8")
    print(f"[ui_inspector] 控件树已写入: {path}")
    return root


# ══════════════════════════════════════════════════════════════════════════════
# 2. 高亮绘制引擎（单一后台 Tk 线程，非阻塞）
# ══════════════════════════════════════════════════════════════════════════════

_tk_queue: queue.Queue = queue.Queue()
_tk_thread: Optional[threading.Thread] = None
_tk_root: Optional[tk.Tk] = None
_tk_lock = threading.Lock()

_TRANSPARENT = "black"   # 透明镂空色（不要在 UI 里真正用黑色背景）


def _tk_worker():
    global _tk_root
    _tk_root = tk.Tk()
    _tk_root.withdraw()  # 隐藏主窗口，仅作事件循环宿主

    def _pump():
        try:
            while True:
                fn = _tk_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        _tk_root.after(20, _pump)   # 每 20ms 轮询一次任务队列

    _tk_root.after(20, _pump)
    _tk_root.mainloop()


def _ensure_tk():
    global _tk_thread
    with _tk_lock:
        if _tk_thread is None or not _tk_thread.is_alive():
            _tk_thread = threading.Thread(target=_tk_worker, daemon=True)
            _tk_thread.start()
            time.sleep(0.12)   # 等待 Tk 初始化


def highlight(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    duration: float = 2.0,
    color: str = "red",
    border: int = 1,
    label: str = "",
    flash: bool = False,
    flash_interval_ms: int = 350,
):
    """
    在屏幕上叠加高亮矩形框（完全非阻塞）。

    :param x, y:              左上角屏幕坐标
    :param width, height:     矩形尺寸
    :param duration:          显示时长（秒）
    :param color:             边框/标签颜色，任意 tkinter 颜色字符串
    :param border:            边框粗细（像素）
    :param label:             左上角标签文字，留空则不显示
    :param flash:             是否开启边框闪烁动画
    :param flash_interval_ms: 闪烁切换间隔（毫秒）
    """
    if width <= 0 or height <= 0:
        return

    _ensure_tk()

    def _create():
        top = tk.Toplevel(_tk_root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.attributes("-transparentcolor", _TRANSPARENT)   # 黑色区域完全穿透
        top.configure(bg=_TRANSPARENT)
        top.geometry(f"{width}x{height}+{x}+{y}")

        canvas = tk.Canvas(
            top, width=width, height=height,
            highlightthickness=0, bg=_TRANSPARENT
        )
        canvas.pack()

        # ── 边框矩形 ───────────────────────────────────────────────────────
        b = border
        rect_id = canvas.create_rectangle(
            b, b, width - b, height - b,
            outline=color, width=b * 2, fill=""
        )

        # ── 标签（带色块背景）─────────────────────────────────────────────
        if label:
            pad = 3
            tid = canvas.create_text(
                b + pad + 4, b + pad + 4,
                text=label, fill="white",
                anchor="nw", font=("Consolas", 9, "bold"),
                tags="lbl",
            )
            bb = canvas.bbox(tid)
            if bb:
                bg_id = canvas.create_rectangle(
                    bb[0] - pad, bb[1] - pad,
                    bb[2] + pad, bb[3] + pad,
                    fill=color, outline="", tags="lblbg",
                )
                canvas.tag_raise(tid, bg_id)   # 文字浮在色块上方

        # ── 闪烁动画 ──────────────────────────────────────────────────────
        if flash:
            _visible = [True]

            def _toggle():
                _visible[0] = not _visible[0]
                state = "normal" if _visible[0] else "hidden"
                canvas.itemconfigure(rect_id, state=state)
                top.after(flash_interval_ms, _toggle)

            top.after(flash_interval_ms, _toggle)

        # ── 定时销毁 ──────────────────────────────────────────────────────
        top.after(int(duration * 1000), top.destroy)

    _tk_queue.put(_create)


# ══════════════════════════════════════════════════════════════════════════════
# 3. 从 lxml 节点直接高亮
# ══════════════════════════════════════════════════════════════════════════════

def _node_label(node) -> str:
    """从 XML 节点属性自动生成标签文字。"""
    ct   = node.get("ControlType", "").replace("Control", "")
    name = node.get("Name", "")
    aid  = node.get("AutomationId", "")
    parts = [ct]
    if name:
        parts.append(f'"{name}"')
    if aid:
        parts.append(f"#{aid}")
    return " ".join(parts)


def highlight_node(
    node,
    *,
    label: Optional[str] = None,
    **kwargs,
):
    """
    高亮单个 lxml 节点（需序列化时包含 x/y/width/height 属性）。

    :param node:  lxml Element，从 build_tree() 返回的树中取得
    :param label: 自定义标签；None 则自动生成 ControlType + Name + AutomationId
    :param kwargs: 透传给 highlight()（color, duration, border, flash…）
    """
    x      = int(node.get("x",      0))
    y      = int(node.get("y",      0))
    width  = int(node.get("width",  0))
    height = int(node.get("height", 0))

    if width <= 0 or height <= 0:
        name = node.get("Name", node.tag)
        print(f"[highlight_node] 跳过「{name}」—— 无有效坐标（IsOffscreen?）")
        return

    lbl = label if label is not None else _node_label(node)
    highlight(x, y, width, height, label=lbl, **kwargs)


# 多色循环，用于批量高亮时区分不同节点
_PALETTE = ["red", "#00c8ff", "lime", "#ff9900", "#ff00ff", "#ffff00"]


def highlight_nodes(
    nodes,
    *,
    color: Union[str, list[str], None] = None,
    duration: float = 2.5,
    stagger_ms: int = 0,
    **kwargs,
):
    """
    批量高亮多个 lxml 节点。

    :param nodes:      可迭代的 lxml Element 列表（XPath 结果）
    :param color:      单色字符串 / 颜色列表（循环使用）/ None 则自动轮换调色板
    :param duration:   每个高亮的显示时长（秒）
    :param stagger_ms: 每个节点之间的延迟（毫秒），0 = 同时显示
    :param kwargs:     透传给 highlight_node()
    """
    nodes = list(nodes)
    if not nodes:
        print("[highlight_nodes] 没有节点需要高亮")
        return

    if color is None:
        colors = _PALETTE
    elif isinstance(color, str):
        colors = [color]
    else:
        colors = list(color)

    _ensure_tk()

    def _schedule_all():
        for i, node in enumerate(nodes):
            delay = i * stagger_ms

            def _make_task(n, c):
                def _task():
                    highlight_node(n, color=c, duration=duration, **kwargs)
                return _task

            c = colors[i % len(colors)]
            if delay > 0:
                # 借用 Tk after() 来实现延迟，无需额外线程
                _tk_root.after(delay, _make_task(node, c))
            else:
                _make_task(node, c)()

    _tk_queue.put(_schedule_all)




# ══════════════════════════════════════════════════════════════════════════════
# 示例
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # ── UIAutomation + XPath 完整流程 ────────────────────────────────────────
    if auto is None or etree is None:
        print("跳过 UIAutomation 演示（未安装依赖）")
        sys.exit(0)

    print("\n抓取「记事本」控件树并用 XPath 查询…")
    try:
        win = auto.WindowControl(Name="无标题.txt - Notepad", searchDepth=2)
        root = build_tree(win, max_depth=10)

        # 输出 XML 供调试
        dump_xml(win, "notepad_tree.xml")

        # XPath 查询示例
        edits   = root.xpath('//TextControl[@Name="查看"]')
        # buttons = root.xpath('//ButtonControl')
        # menus   = root.xpath('//MenuBarControl/MenuItemControl')

        # print(f"EditControl ×{len(edits)}  ButtonControl ×{len(buttons)}  MenuItem ×{len(menus)}")

        # 批量高亮，交错 150ms 显示
        highlight_nodes(edits,   color="red",    duration=3, stagger_ms=150)
        # highlight_nodes(buttons, color="#00c8ff", duration=3, stagger_ms=150)
        # highlight_nodes(menus,   color="lime",   duration=3, stagger_ms=150)


    except Exception as e:
        print(f"UIAutomation 演示失败: {e}")

    time.sleep(4)
