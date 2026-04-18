# win_ui_auto/hooks/hl.py
import sys
import time
import fnmatch
import ctypes
import uiautomation as auto
from highlight import HighlightWindow
from control_info import is_same_control
from hooks.locator import locate_by_xpath, locate_all_by_xpath


def _dedupe_controls(items):
    out = []
    for m in items:
        if not any(is_same_control(m, x) for x in out):
            out.append(m)
    return out

def force_focus_window(el):
    """强制将控件所属的顶层窗口置顶并恢复显示 (与 clk 保持逻辑一致)"""
    try:
        top_level = el.GetTopLevelControl()
        if not top_level:
            return
        
        hwnd = top_level.NativeWindowHandle
        if not hwnd:
            return

        user32 = ctypes.windll.user32
        # SW_RESTORE = 9: 如果窗口最小化，则恢复它
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        
        user32.SetForegroundWindow(hwnd)
        # 给系统 0.3 秒的窗口绘制和动画时间，确保高亮框位置准确
        time.sleep(0.3)
    except Exception as e:
        print(f"[!] 尝试激活窗口失败: {e}")

def get_text_for_match(el):
    """提取用于匹配的文本：Name 或 Value"""
    name = (el.Name or "").strip()
    value = ""
    try:
        if auto.PatternId.ValuePattern in el.GetSupportedPatterns():
            value = (el.GetValuePattern().Value or "").strip()
    except:
        pass
    return name, value

def find_matches_recursive(el, pattern, max_deep, current_deep=0, found_elements=None):
    """递归搜索符合模糊匹配条件的子元素"""
    if found_elements is None:
        found_elements = []
    
    if current_deep > max_deep:
        return found_elements

    name, value = get_text_for_match(el)
    
    # 模糊匹配：支持通配符
    if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(value, pattern):
        rect = el.BoundingRectangle
        if rect and rect.width() > 0:
            found_elements.append(el)

    try:
        children = el.GetChildren()
        for child in children:
            find_matches_recursive(child, pattern, max_deep, current_deep + 1, found_elements)
    except:
        pass
    
    return found_elements

def run(xpath, timeout=10.0, match_pattern=None, deep=0, index=None):
    # 1. 定位基准
    final_targets = []
    if match_pattern:
        search_pattern = match_pattern if "*" in match_pattern else f"*{match_pattern}*"
        candidates = locate_all_by_xpath(xpath, timeout=timeout)
        if not candidates:
            base_el = locate_by_xpath(xpath, timeout)
            candidates = [base_el] if base_el else []
        if not candidates:
            print(f"\n❌ 最终结果：未找到基准元素。")
            sys.exit(1)
        print(
            f"[*] 在 XPath 最后一档匹配的 {len(candidates)} 个实例下，"
            f"深度搜索 Name/Value 匹配 '{search_pattern}' 的控件..."
        )
        merged = []
        for c in candidates:
            merged.extend(find_matches_recursive(c, search_pattern, deep))
        final_targets = _dedupe_controls(merged)
    else:
        # 最后一档（如相同 AutomationId 的多个 Button）全部枚举，避免只高亮 foundIndex=1
        final_targets = locate_all_by_xpath(xpath, timeout=timeout)
        if not final_targets:
            print(f"\n❌ 最终结果：未找到匹配元素。")
            sys.exit(1)
        if len(final_targets) > 1:
            print(f"[*] XPath 在最后一档共命中 {len(final_targets)} 个控件，将依次高亮。")

    if not final_targets:
        print(f"❌ 未找到任何匹配项。")
        sys.exit(1)

    # 3. 初始化高亮窗口
    hw = HighlightWindow()
    
    try:
        if index is not None:
            idx = index - 1
            if 0 <= idx < len(final_targets):
                target = final_targets[idx]
                
                # --- 【核心增强】高亮前先置顶窗口 ---
                print(f"[*] 激活并置顶目标窗口...")
                force_focus_window(target)
                
                rect = target.BoundingRectangle
                print(f"✅ 匹配成功：正在高亮第 {index} 个 - [{target.ControlTypeName}] {target.Name}")
                hw.update(rect.left, rect.top, rect.width(), rect.height())
                time.sleep(3) 
            else:
                print(f"❌ 索引越界（共 {len(final_targets)} 个匹配项，有效 --index 为 1..{len(final_targets)}）。")
                sys.exit(1)
        else:
            # 批量高亮逻辑（含「同 XPath 多实例」全部闪烁）
            print(f"✅ 准备激活窗口并循环高亮 {len(final_targets)} 个匹配项...")
            # 批量时仅在开始前置顶一次
            force_focus_window(final_targets[0])
            
            for target in final_targets:
                rect = target.BoundingRectangle
                hw.update(rect.left, rect.top, rect.width(), rect.height())
                time.sleep(0.6) # 稍微加长闪烁时间
            time.sleep(1)
    finally:
        hw.clear()
        hw.stop()

    return True
