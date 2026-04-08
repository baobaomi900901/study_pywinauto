# get_ui_tree.py
# 通过进程 PID 生成 UIAutomation 控件树 XML 文件
#
# 依赖: pip install uiautomation lxml

from __future__ import annotations

import sys
import time
from typing import Optional

try:
    import uiautomation as auto
except ImportError:
    auto = None

try:
    from lxml import etree
except ImportError:
    etree = None


# ══════════════════════════════════════════════════════════════════════════════
# 1. 控件树序列化
# ══════════════════════════════════════════════════════════════════════════════

def build_tree(control, parent=None, *, max_depth: int = 32, _depth: int = 0):
    """
    将 UIAutomation 控件树序列化为 lxml ElementTree。
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
    """将控件树保存为 XML 文件"""
    if etree is None:
        print("错误：未安装 lxml 库")
        return None

    root = build_tree(control)
    if root is None:
        print("build_tree 返回为空")
        return None

    tree = etree.ElementTree(root)
    with open(path, "wb") as f:
        tree.write(f, pretty_print=pretty, xml_declaration=True, encoding="utf-8")

    print(f"[dump_xml] 控件树已写入: {path}")
    return root


# ══════════════════════════════════════════════════════════════════════════════
# 2. 通过 PID 生成 UI 树 XML（核心功能）
# ══════════════════════════════════════════════════════════════════════════════

def dump_xml_by_pid(
    pid: int,
    path: Optional[str] = None,
    *,
    max_depth: int = 200,
    pretty: bool = True,
    window_name: Optional[str] = None
) -> Optional[etree.Element]:
    """
    通过进程 PID 生成该应用的 UI 控件树 XML 文件

    参数:
        pid          : 目标进程的 PID（必填）
        path         : 输出 XML 文件路径，默认为 ui_tree_{pid}.xml
        max_depth    : 控件树最大递归深度（防止卡死）
        pretty       : 是否格式化 XML 输出
        window_name  : 可选，指定窗口名称过滤（当一个进程有多个窗口时使用）

    返回:
        lxml Element 根节点（成功时），失败返回 None
    """
    if auto is None:
        print("错误：未安装 uiautomation 库，请执行: pip install uiautomation")
        return None
    if etree is None:
        print("错误：未安装 lxml 库，请执行: pip install lxml")
        return None

    if path is None:
        path = f"ui_tree_{pid}.xml"

    try:
        print(f"[dump_xml_by_pid] 正在查找 PID = {pid} 的窗口...")

        root_control = auto.GetRootControl()

        # 第一步：尝试在顶级窗口中查找
        target_window = None
        for child in root_control.GetChildren():
            if child.ProcessId == pid:
                if window_name is None or window_name in child.Name:
                    target_window = child
                    break

        # 第二步：如果没找到，尝试全局搜索（更彻底）
        if target_window is None:
            print(f"[dump_xml_by_pid] 顶级窗口未找到，尝试全局搜索 PID={pid}...")
            condition = auto.Condition.create(ProcessId=pid)
            all_controls = root_control.FindAll(auto.TreeScope.Descendants, condition)

            for ctrl in all_controls:
                if ctrl.ControlType == auto.ControlType.WindowControl and not ctrl.IsOffscreen:
                    if window_name is None or window_name in ctrl.Name:
                        target_window = ctrl
                        break

            # 仍未找到则取第一个匹配的控件作为兜底
            if target_window is None and all_controls:
                target_window = all_controls[0]

        if target_window is None:
            print(f"[dump_xml_by_pid] 错误：未找到 PID={pid} 对应的窗口")
            return None

        print(f"[dump_xml_by_pid] ✓ 找到窗口: \"{target_window.Name}\" (PID={pid})")

        # 生成控件树并保存为 XML
        root_elem = build_tree(target_window, max_depth=max_depth)
        if root_elem is None:
            print("[dump_xml_by_pid] build_tree 失败")
            return None

        tree = etree.ElementTree(root_elem)
        with open(path, "wb") as f:
            tree.write(f, pretty_print=pretty, xml_declaration=True, encoding="utf-8")

        # 统计控件数量
        total_nodes = len(list(root_elem.iter()))

        print(f"[dump_xml_by_pid] ✓ 成功生成 XML 文件！")
        print(f"                  文件路径: {path}")
        print(f"                  窗口名称: {target_window.Name}")
        print(f"                  控件总数: {total_nodes}")
        print(f"                  最大深度: {max_depth}")

        return root_elem

    except Exception as e:
        print(f"[dump_xml_by_pid] 生成 XML 时发生异常 (PID={pid}): {e}")
        import traceback
        traceback.print_exc()
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 示例使用
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if auto is None or etree is None:
        print("请先安装依赖：")
        print("   pip install uiautomation lxml")
        sys.exit(1)

    # 从命令行参数获取 PID
    if len(sys.argv) < 2:
        print("用法: python get_ui_tree.py <PID> [--window-name <名称片段>] [--output <文件路径>]")
        print("示例: python get_ui_tree.py 8632")
        sys.exit(1)

    try:
        target_pid = int(sys.argv[1])
    except ValueError:
        print(f"错误：PID 必须是整数，收到 '{sys.argv[1]}'")
        sys.exit(1)

    # 可选参数解析（简单实现）
    window_name = None
    output_path = None
    for i in range(2, len(sys.argv)):
        if sys.argv[i] == "--window-name" and i + 1 < len(sys.argv):
            window_name = sys.argv[i + 1]
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]

    print("=" * 60)
    print("开始通过 PID 生成 UI 控件树 XML")
    print("=" * 60)

    dump_xml_by_pid(
        pid=target_pid,
        path=output_path,          # 若为 None 则自动生成 ui_tree_{pid}.xml
        max_depth=20,
        window_name=window_name
    )

    print("\n操作完成！")