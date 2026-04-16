# win_ui_auto/hooks/clk.py
import sys
import time
import fnmatch
import ctypes
import uiautomation as auto
from hooks.locator import locate_by_xpath
from constants import DEBUG

def force_focus_window(el):
    """强制将控件所属的顶层窗口置顶并恢复显示"""
    try:
        # 获取控件所属的顶层窗口句柄
        top_level = el.GetTopLevelControl()
        if not top_level:
            return
        
        hwnd = top_level.NativeWindowHandle
        if not hwnd:
            return

        user32 = ctypes.windll.user32
        # 1. 如果窗口被最小化了，先恢复它 (SW_RESTORE = 9)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        
        # 2. 强行置顶
        user32.SetForegroundWindow(hwnd)
        # 给系统 0.2 秒的窗口切换和重绘时间
        time.sleep(0.2)
    except Exception as e:
        print(f"[!] 尝试置顶窗口失败: {e}")

def get_text_for_match(el):
    name = (el.Name or "").strip()
    value = ""
    try:
        if auto.PatternId.ValuePattern in el.GetSupportedPatterns():
            value = (el.GetValuePattern().Value or "").strip()
    except:
        pass
    return name, value

def find_matches_recursive(el, pattern, max_deep, current_deep=0, found_elements=None):
    if found_elements is None:
        found_elements = []
    if current_deep > max_deep:
        return found_elements

    name, value = get_text_for_match(el)
    search_pattern = pattern if "*" in pattern else f"*{pattern}*"
    
    if fnmatch.fnmatch(name, search_pattern) or fnmatch.fnmatch(value, search_pattern):
        # 点击动作必须要求元素是可交互的 (通常有坐标即可)
        rect = el.BoundingRectangle
        if rect and rect.width() > 0:
            found_elements.append(el)

    try:
        for child in el.GetChildren():
            find_matches_recursive(child, pattern, max_deep, current_deep + 1, found_elements)
    except:
        pass
    return found_elements

def run(xpath, timeout=10.0, match_pattern=None, deep=0, index=None):
    # 1. 定位基准
    base_el = locate_by_xpath(xpath, timeout)
    if not base_el:
        if DEBUG:
            print(f"\n❌ 最终结果：未找到基准元素。")
        print(False)
        return False
        sys.exit(1)

    # 2. 查找目标
    final_targets = []
    if match_pattern:
        if DEBUG:
            print(f"[*] 正在基准元素下搜索匹配 '{match_pattern}' 的子元素...")
        final_targets = find_matches_recursive(base_el, match_pattern, deep)
    else:
        final_targets = [base_el]

    if not final_targets:
        print(f"❌ 未找到匹配项，无法执行点击。")
        sys.exit(1)

    # 3. 确定最终执行对象
    target_to_click = None
    if index is not None:
        idx = index - 1
        if 0 <= idx < len(final_targets):
            target_to_click = final_targets[idx]
        else:
            print(f"❌ 索引 {index} 越界。")
            sys.exit(1)
    else:
        # 如果没填 index，默认点击第一个匹配到的
        target_to_click = final_targets[0]

    # 4. 【核心强化】执行点击前置动作：置顶
    if DEBUG:
        print(f"[*] 正在激活目标窗口并置顶...")
    force_focus_window(target_to_click)

    # 5. 执行点击
    try:
        rect = target_to_click.BoundingRectangle
        if DEBUG:
            print(f"✅ 准备点击: [{target_to_click.ControlTypeName}] {target_to_click.Name} @ ({rect.left + rect.width()//2}, {rect.top + rect.height()//2})")
        
        # 使用 Click() 会模拟物理点击，如果元素被遮挡有时会失效
        # 建议先移动再点击，或者直接调用 Pattern 的 Invoke
        target_to_click.Click(simulateMove=False)
        if DEBUG:
            print("[+] 点击指令发送成功。")
        print(True) 
        return True
    
    except Exception as e:
        print(f"❌ 点击失败: {e}")
        sys.exit(1)

    return True
