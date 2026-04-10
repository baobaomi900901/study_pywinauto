# win_ui_auto/hooks/get_ui_tree.py
# 通过进程 PID 生成 UIAutomation 控件树 XML 文件（优化版 + 自定义输出路径）

from __future__ import annotations
import sys
import time
import argparse
import os
from typing import Optional

try:
    import uiautomation as auto
except ImportError:
    auto = None

try:
    from lxml import etree
except ImportError:
    etree = None

try:
    import psutil
except ImportError:
    psutil = None


# ══════════════════════════════════════════════════════════════════════════════
# 1. 控件树序列化
# ══════════════════════════════════════════════════════════════════════════════
def build_tree(
    control,
    parent: Optional[etree.Element] = None,
    *,
    max_depth: int = 18,
    _depth: int = 0,
    start_time: float = 0.0,
    timeout: float = 15.0,
    node_count: list[int],
) -> Optional[etree.Element]:
    """将 UIAutomation 控件递归序列化为 lxml ElementTree（带超时和异常保护）"""
    if _depth > max_depth:
        return None
    if time.time() - start_time > timeout:
        print(f"[build_tree] 警告：构建超时（已达 {timeout} 秒），停止继续递归")
        return None

    tag = (control.ControlTypeName or "Unknown").replace(" ", "")

    try:
        rect = control.BoundingRectangle
        x, y, w, h = rect.left, rect.top, rect.width(), rect.height()
    except Exception:
        x = y = w = h = 0

    attrs = {
        "Name": control.Name or "",
        "AutomationId": control.AutomationId or "",
        "ClassName": control.ClassName or "",
        "ControlType": control.ControlTypeName or "",
        "IsEnabled": str(control.IsEnabled),
        "IsOffscreen": str(control.IsOffscreen),
        "x": str(x),
        "y": str(y),
        "width": str(w),
        "height": str(h),
    }

    elem = etree.SubElement(parent, tag, attrs) if parent is not None else etree.Element(tag, attrs)
    node_count[0] += 1

    for child in control.GetChildren():
        build_tree(
            child, elem,
            max_depth=max_depth,
            _depth=_depth + 1,
            start_time=start_time,
            timeout=timeout,
            node_count=node_count,
        )
    return elem


# ══════════════════════════════════════════════════════════════════════════════
# 2. 通过 PID 查找窗口
# ══════════════════════════════════════════════════════════════════════════════
def find_window_by_pid(pid: int, window_name: Optional[str] = None, timeout: float = 5.0):
    """高效查找目标窗口"""
    if auto is None:
        return None

    root = auto.GetRootControl()

    # 优先使用 searchDepth=1
    try:
        window = auto.WindowControl(searchDepth=1, ProcessId=pid)
        if window.Exists(maxSearchSeconds=2):
            name = window.Name or ""
            if window_name is None or window_name in name:
                print(f"[find_window] ✓ 使用 searchDepth=1 找到窗口: \"{name}\" (PID={pid})")
                return window
    except Exception:
        pass

    # 兜底搜索顶级窗口
    condition = auto.Condition.create(ProcessId=pid)
    top_windows = root.FindAll(auto.TreeScope.Children, condition)

    for win in top_windows:
        if win.ControlType == auto.ControlType.WindowControl and not win.IsOffscreen:
            name = win.Name or ""
            if window_name is None or window_name in name:
                print(f"[find_window] ✓ 在顶级窗口中找到: \"{name}\" (PID={pid})")
                return win

    print(f"[find_window] 错误：未找到 PID={pid} 对应的窗口")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 3. 生成 XML（核心函数，已修改默认路径）
# ══════════════════════════════════════════════════════════════════════════════
def dump_xml_by_pid(
    pid: int,
    path: Optional[str] = None,
    *,
    max_depth: int = 18,
    pretty: bool = True,
    window_name: Optional[str] = None,
    timeout: float = 15.0,
) -> Optional[etree.Element]:
    """通过 PID 生成 UI 控件树 XML"""
    if auto is None or etree is None:
        print("错误：请先安装依赖：pip install uiautomation lxml")
        return None

    # ==================== 修改默认路径的核心逻辑 ====================
    if path is None:
        # 默认保存到 .\ui_tree\ 目录下
        output_dir = os.path.join(os.getcwd(), "ui_tree")
        os.makedirs(output_dir, exist_ok=True)          # 自动创建文件夹
        path = os.path.join(output_dir, f"ui_tree_{pid}.xml")
    # ============================================================

    # 检查进程是否存在（可选）
    if psutil is not None:
        try:
            if not psutil.pid_exists(pid):
                print(f"[警告] PID={pid} 的进程不存在或已退出")
        except Exception:
            pass

    print(f"[dump_xml_by_pid] 正在查找 PID = {pid} 的窗口...")
    target_window = find_window_by_pid(pid, window_name)

    if target_window is None:
        return None

    print(f"[dump_xml_by_pid] 开始构建控件树 (max_depth={max_depth}, timeout={timeout}s)...")
    start_time = time.time()
    node_count = [0]

    root_elem = build_tree(
        target_window,
        max_depth=max_depth,
        start_time=start_time,
        timeout=timeout,
        node_count=node_count,
    )

    if root_elem is None:
        print("[dump_xml_by_pid] build_tree 失败或超时")
        return None

    total_nodes = node_count[0]
    use_pretty = pretty and total_nodes <= 2000
    if pretty and total_nodes > 2000:
        print(f"[提示] 控件数量较多 ({total_nodes})，自动关闭 pretty_print")

    # 保存 XML（已修复编码问题）
    tree = etree.ElementTree(root_elem)
    try:
        with open(path, "wb") as f:
            tree.write(
                f,
                pretty_print=use_pretty,
                xml_declaration=True,
                encoding="utf-8"
            )

        elapsed = time.time() - start_time
        print(f"[dump_xml_by_pid] ✓ 成功生成 XML 文件！")
        print(f"                  文件路径: {path}")
        print(f"                  窗口名称: {target_window.Name}")
        print(f"                  控件总数: {total_nodes}")
        print(f"                  耗时: {elapsed:.2f} 秒")
        return root_elem
    except Exception as e:
        print(f"[dump_xml_by_pid] 保存 XML 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 4. 命令行入口
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if auto is None or etree is None:
        print("请先安装依赖：pip install uiautomation lxml")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="通过进程 PID 生成 UIAutomation 控件树 XML 文件",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("pid", type=int, help="目标进程的 PID")
    parser.add_argument("-o", "--output", type=str, help="自定义输出 XML 文件完整路径")
    parser.add_argument("-w", "--window-name", type=str, help="窗口名称过滤")
    parser.add_argument("-d", "--max-depth", type=int, default=18, help="最大递归深度")
    parser.add_argument("-t", "--timeout", type=float, default=15.0, help="构建超时时间（秒）")
    parser.add_argument("--no-pretty", action="store_true", help="禁用 XML 美化")

    args = parser.parse_args()

    print("=" * 70)
    print("开始通过 PID 生成 UI 控件树 XML")
    print("=" * 70)

    dump_xml_by_pid(
        pid=args.pid,
        path=args.output,
        max_depth=args.max_depth,
        pretty=not args.no_pretty,
        window_name=args.window_name,
        timeout=args.timeout,
    )

    print("\n操作完成！")


if __name__ == "__main__":
    main()