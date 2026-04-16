# win_ui_auto/hooks/locator.py
import time
import re
import uiautomation as auto
import ctypes
from ctypes import wintypes

try:
    import psutil
except ImportError:
    psutil = None

def bridge_to_renderer(top_hwnd):
    """HWND 底层穿透：寻找真实的渲染窗口，绕过 CEF 的 UIA 树断层"""
    hwnds = []
    user32 = ctypes.windll.user32
    
    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if "Chrome_RenderWidgetHostHWND" in buf.value or "Render" in buf.value:
            # 【致命修复】删除了 IsWindowVisible 的限制！
            # 因为 CEF 架构经常使用离屏渲染，画布本身在系统层面可能是隐藏的，但我们必须强抓它！
            hwnds.append(h)
        return True
        
    EnumChildProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(top_hwnd, EnumChildProcType(enum_child_proc), 0)
    
    docs = []
    for h in hwnds:
        try:
            docs.append(auto.ControlFromHandle(h))
        except:
            pass
    return docs


def locate_by_xpath(xpath, timeout=10.0):
    print(f"[*] 启动 XPath 逆向解析引擎...")
    
    clean_xpath = xpath.replace("///", "//").replace("//", "/descendant::")
    segments = [s for s in clean_xpath.split('/') if s]
    
    steps = []
    for seg in segments:
        depth = 1
        if seg.startswith("descendant::"):
            depth = 8 # 【修复】深度调大，CEF 套娃非常深
            seg = seg.replace("descendant::", "")
            
        type_match = re.match(r"^([a-zA-Z]+)", seg)
        if not type_match: continue
        ctype_name = type_match.group(1)
        ctype_name = ctype_name + "Control" if not ctype_name.endswith("Control") else ctype_name
        
        # 【修复】增强正则：兼容单双引号，确保 ProcessName 绝对能被提取出来
        attrs = {}
        for attr_match in re.finditer(r"\[@([a-zA-Z0-9_]+)=['\"]([^'\"]+)['\"]\]", seg):
            attrs[attr_match.group(1)] = attr_match.group(2)
            
        index = 1
        idx_match = re.search(r"\[(\d+)\]$", seg)
        if idx_match:
            index = int(idx_match.group(1))
            
        steps.append({
            "raw": seg,
            "type_name": ctype_name,
            "attrs": attrs,
            "index": index,
            "depth": depth
        })

    current_node = auto.GetRootControl()
    start_time = time.time()
    
    for i, step in enumerate(steps):
        if time.time() - start_time > timeout:
            print(f"[-] 寻址超时！折戟于第 {i+1} 层。")
            return None
            
        # ==========================================
        # 特权通道：顶层应用锁定
        # ==========================================
        if i == 0 and "ProcessName" in step["attrs"]:
            pname = step["attrs"]["ProcessName"].lower()
            print(f" -> [特权通道] 正在扫描内存进程，锁定应用外壳: {pname} ...")
            found_node = None
            if psutil:
                for child in current_node.GetChildren():
                    try:
                        if child.ProcessId and psutil.Process(child.ProcessId).name().lower() == pname:
                            found_node = child
                            break
                    except:
                        pass
            
            if found_node:
                current_node = found_node
                print(f"    [+] 锁定成功！目标 PID: {current_node.ProcessId}")
                continue  # 跳过底下的原生搜索，直接进入下一层（Document）
            else:
                print(f"[-] 致命错误：当前系统未找到运行的 {pname} 进程对应的可见窗口。")
                return None

        # ==========================================
        # 常规 UIA 寻路
        # ==========================================
        search_kwargs = {
            "searchFromControl": current_node,
            "searchDepth": step["depth"],
            "foundIndex": step["index"]
        }
        
        if hasattr(auto.ControlType, step["type_name"]):
            search_kwargs["ControlType"] = getattr(auto.ControlType, step["type_name"])
            
        # 【致命修复】忽略 Document 层级的 ClassName，防止 UIA 被虚假属性骗到
        if "ClassName" in step["attrs"]:
            if step["type_name"] == "DocumentControl" and "Chrome" in step["attrs"]["ClassName"]:
                pass 
            else:
                search_kwargs["ClassName"] = step["attrs"]["ClassName"]
                
        if "Name" in step["attrs"]:
            search_kwargs["Name"] = step["attrs"]["Name"]
            
        print(f" -> 逐层破解 [{i+1}/{len(steps)}]: 检索 {step['raw']} ...")
        
        try:
            next_node = auto.Control(**search_kwargs)
            
            # 【修复】CEF 渲染非常缓慢，把寻路容忍时间从 0.5 秒拉长到 3.0 秒
            if not next_node.Exists(3.0, 0.2):
                if step["type_name"] == "DocumentControl" and current_node.NativeWindowHandle:
                    print(f"    [!] 检测到 UIA 树虚假断裂，启动 HWND 底层穿透...")
                    docs = bridge_to_renderer(current_node.NativeWindowHandle)
                    target_idx = step["index"] - 1
                    if docs and target_idx < len(docs):
                        print(f"    [+] 穿透成功！强行捕获到底层渲染画布！")
                        current_node = docs[target_idx]
                        continue
                        
                print(f"[-] 坐标反推失败：UIA 树在 {step['raw']} 处彻底断裂。")
                return None
                
            current_node = next_node
        except Exception as e:
            print(f"[-] 寻址发生崩溃: {e}")
            return None

    return current_node
