import sys
import os
import argparse
import re
import time
import json
import ctypes
from ctypes import wintypes
import uiautomation as auto

# 确保可以导入父目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_render_hwnds_in_window(main_hwnd):
    """架构嗅探：只在指定的主窗口句柄下搜寻 Chrome 渲染底板"""
    hwnds = []
    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(h, buf, 256)
        if buf.value == "Chrome_RenderWidgetHostHWND":
            hwnds.append(h)
        return True

    enum_ptr = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_child_proc)
    ctypes.windll.user32.EnumChildWindows(main_hwnd, enum_ptr, 0)
    return hwnds


def force_wake_up_chromium(hwnd):
    """底层 COM 强索：逼迫休眠的 Chromium 瞬间序列化 DOM 树"""
    try:
        oleacc = ctypes.windll.oleacc
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), 
                        ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

        IID_IAccessible = GUID(0x618736e0, 0x3c3d, 0x11cf, (0x81, 0x0c, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71))
        OBJID_CLIENT = -4
        pacc = ctypes.c_void_p()
        oleacc.AccessibleObjectFromWindow(hwnd, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pacc))
    except:
        pass


def parse_xpath(xpath_str):
    """将简化的 XPath 解析为结构化字典"""
    if xpath_str.startswith('//'):
        xpath_str = xpath_str[2:]
    xpath_str = xpath_str.lstrip('/')
    steps = xpath_str.split('/')
    result = []
    for step in steps:
        if not step: continue
        match = re.match(r'^(\w+)(.*)$', step)
        if not match: continue
        control_type = match.group(1)
        predicates = match.group(2).strip()
        attrs = {}
        position = None
        for block in re.findall(r'\[(.*?)\]', predicates):
            block = block.strip()
            if '=' in block:
                attr_match = re.match(r'@(\w+)=[\'"](.+?)[\'"]', block)
                if attr_match:
                    k, v = attr_match.groups()
                    attrs[k] = v
            else:
                try: position = int(block)
                except: pass
        result.append((control_type, attrs, position))
    return result


def locate_lightning(steps, timeout=10):
    """【全能自适应闪电战】自动识别原生应用与Chromium应用并采用最佳穿透策略"""
    if not steps: return None
    
    # 1. 锁定顶级主窗口 (XPath 第一层)
    win_type, win_attrs, _ = steps[0]
    search_kwargs = {"searchDepth": 1}
    if 'ClassName' in win_attrs: search_kwargs['ClassName'] = win_attrs['ClassName']
    if 'Name' in win_attrs: search_kwargs['Name'] = win_attrs['Name']
    
    target_window = auto.WindowControl(**search_kwargs)
    if not target_window.Exists(0.5):
        print(f"[错误] 找不到目标主窗口: {search_kwargs}", file=sys.stderr)
        return None
        
    main_hwnd = target_window.NativeWindowHandle
    
    # 2. 嗅探底层架构：判断该窗口内是否真的有 Chromium 渲染底板
    render_hwnds = get_render_hwnds_in_window(main_hwnd)
    
    if render_hwnds:
        # ==========================================
        # 分支 A：Chromium 穿透逻辑 (针对微信、钉钉等)
        # ==========================================
        doc_index = -1
        for i, step in enumerate(steps):
            if step[0] == "Document":
                doc_index = i
                break
                
        if doc_index != -1:
            print(f"[闪电战] 嗅探到 Chromium 架构，准备下潜...", file=sys.stderr)
            virtual_steps = steps[doc_index + 1:]
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                for hwnd in render_hwnds:
                    force_wake_up_chromium(hwnd)
                    try:
                        current = auto.ControlFromHandle(hwnd)
                        success = True
                        for ctrl_type, attrs, position in virtual_steps:
                            matched = []
                            for child in current.GetChildren():
                                ctype = child.ControlTypeName.replace("Control", "")
                                if (ctype == ctrl_type or ctrl_type == "*"):
                                    ok = True
                                    for k, v in attrs.items():
                                        if getattr(child, k, None) != v:
                                            ok = False; break
                                    if ok: matched.append(child)
                            
                            target_idx = (position - 1) if position else 0
                            if target_idx < len(matched):
                                current = matched[target_idx]
                            else:
                                success = False; break
                                
                        if success:
                            cost = time.time() - start_time
                            print(f"[闪电战] Chromium 穿透成功！耗时: {cost:.2f}秒", file=sys.stderr)
                            return current
                    except: pass
                time.sleep(0.1)
                
    # ==========================================
    # 分支 B：原生 UIA 兜底逻辑 (针对记事本、系统设置等纯原生应用)
    # ==========================================
    print("[闪电战] 检测为原生应用，启动纯 UIA 精准定位引擎...", file=sys.stderr)
    current = target_window
    start_time = time.time()
    
    # 从第二层（跳过第一层的 Window）开始逐层往下比对
    for i in range(1, len(steps)):
        ctrl_type, attrs, position = steps[i]
        found = False
        
        while time.time() - start_time < timeout:
            matched = []
            for child in current.GetChildren():
                ctype = child.ControlTypeName.replace("Control", "")
                if ctype == ctrl_type or ctrl_type == "*":
                    ok = True
                    for k, v in attrs.items():
                        if getattr(child, k, None) != v:
                            ok = False; break
                    if ok: matched.append(child)
            
            target_idx = (position - 1) if position else 0
            if target_idx < len(matched):
                current = matched[target_idx]
                found = True
                break
            else:
                # 给界面一点加载的时间，特别是处理需要动态展开的菜单时
                time.sleep(0.1) 
                
        if not found:
            print(f"[错误] 定位断裂：在 '{ctrl_type}' 层未能找到匹配控件", file=sys.stderr)
            return None
            
    print(f"[闪电战] UIA 精准定位成功！耗时: {time.time() - start_time:.2f}秒", file=sys.stderr)
    return current


def collect_child_texts(control, max_depth=1, current_depth=0):
    """全能文本抓取器：兼容编辑框(Value)与普通控件(Name)"""
    texts = []
    content = None
    
    # 优先尝试获取 Value (针对 Notepad 文档、文本框等输入类控件)
    try:
        if hasattr(control, 'GetValuePattern'):
            val = control.GetValuePattern().Value
            if val: content = val
    except: pass
    
    # 退而求其次获取 Name (针对按钮、标签等静态控件)
    if not content and control.Name:
        content = control.Name
        
    if content: 
        texts.append(content)

    # 递归遍历子节点
    if current_depth < max_depth:
        for child in control.GetChildren():
            texts.extend(collect_child_texts(child, max_depth, current_depth + 1))
            
    # 结果清洗：去重并剔除纯空白行（保持原有顺序）
    res = []
    seen = set()
    for t in texts:
        t_strip = t.strip()
        if t_strip and t_strip not in seen:
            res.append(t_strip)
            seen.add(t_strip)
            
    return res


def run(xpath, depth=1, timeout=10):
    try:
        steps = parse_xpath(xpath)
        with auto.UIAutomationInitializerInThread():
            control = locate_lightning(steps, timeout=timeout)
            if control is None:
                print("无法定位控件", file=sys.stderr)
                return None

            # 执行抓取
            texts = collect_child_texts(control, max_depth=depth)
            print("\n[抓取结果]:")
            # 确保中文不会被转义为 \uXXXX 格式
            print(json.dumps(texts, ensure_ascii=False))
            return texts
            
    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xpath", type=str)
    parser.add_argument("depth", type=int, nargs='?', default=1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    if args.depth < 0:
        sys.exit(1)
        
    run(args.xpath, args.depth, args.timeout)


if __name__ == "__main__":
    main()