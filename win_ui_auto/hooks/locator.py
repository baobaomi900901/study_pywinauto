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

from constants import DEBUG
from process_utils import get_process_name

def _debug(msg: str):
    if DEBUG:
        try:
            print(msg)
        except Exception:
            pass

def _unescape_xpath_string(v: str) -> str:
    # xpath_generator.py 会把单引号转成 &apos;；这里还原，避免 UIA 精确匹配失败
    # 只做最小集还原，避免引入 XML/HTML 解析复杂度
    return (v or "").replace("&apos;", "'")

def _matches_attrs(ctrl, attrs: dict) -> bool:
    """在已找到的 ctrl 上校验 attrs（用于 ProcessName 锚点后不丢约束）"""
    try:
        cls = attrs.get("ClassName")
        if cls is not None and (ctrl.ClassName or "") != cls:
            return False
        name = attrs.get("Name")
        if name is not None and (ctrl.Name or "") != name:
            return False
        aid = attrs.get("AutomationId")
        if aid is not None and (ctrl.AutomationId or "") != aid:
            return False
    except Exception:
        return False
    return True

def _locate_from_node(start_node, steps, start_index, start_time, timeout):
    """从指定 start_node 开始执行剩余 steps（不再处理 ProcessName 特权通道）。"""
    current_node = start_node

    for j in range(start_index, len(steps)):
        step = steps[j]

        if time.time() - start_time > timeout:
            if DEBUG:
                print(f"[-] 寻址超时！折戟于第 {j+1} 层。")
            return None

        search_kwargs = {
            "searchFromControl": current_node,
            "searchDepth": step["depth"],
            "foundIndex": step["index"],
        }

        if hasattr(auto.ControlType, step["type_name"]):
            search_kwargs["ControlType"] = getattr(auto.ControlType, step["type_name"])

        if "ClassName" in step["attrs"]:
            if step["type_name"] == "DocumentControl" and "Chrome" in step["attrs"]["ClassName"]:
                pass
            else:
                search_kwargs["ClassName"] = step["attrs"]["ClassName"]

        if "Name" in step["attrs"]:
            search_kwargs["Name"] = step["attrs"]["Name"]

        if "AutomationId" in step["attrs"]:
            search_kwargs["AutomationId"] = step["attrs"]["AutomationId"]

        if DEBUG:
            _debug(f" -> 逐层破解 [{j+1}/{len(steps)}]: 检索 {step['raw']} ...")

        try:
            next_node = auto.Control(**search_kwargs)

            if not next_node.Exists(3.0, 0.2):
                if DEBUG:
                    _debug(f"    [-] Exists 失败：{step['raw']}")
                if step["type_name"] == "DocumentControl" and current_node.NativeWindowHandle:
                    if DEBUG:
                        _debug(f"    [!] 检测到 UIA 树虚假断裂，启动 HWND 底层穿透...")
                    docs = bridge_to_renderer(current_node.NativeWindowHandle)
                    target_idx = step["index"] - 1
                    if docs and target_idx < len(docs):
                        if DEBUG:
                            _debug(f"    [+] 穿透成功！强行捕获到底层渲染画布！")
                        current_node = docs[target_idx]
                        continue

                if DEBUG:
                    _debug(f"[-] 坐标反推失败：UIA 树在 {step['raw']} 处彻底断裂。")
                return None

            current_node = next_node
        except Exception as e:
            if DEBUG:
                _debug(f"[-] 寻址发生崩溃（step={step['raw']}）: {e}")
            return None

    return current_node

def bridge_to_renderer(top_hwnd):
    """HWND 底层穿透：寻找真实的渲染窗口，绕过 CEF 的 UIA 树断层"""
    hwnds = []
    user32 = ctypes.windll.user32
    
    def enum_child_proc(h, lParam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if "Chrome_RenderWidgetHostHWND" in buf.value or "Render" in buf.value:
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
    if DEBUG:
        _debug(f"[*] 启动 XPath 逆向解析引擎...")
    
    clean_xpath = xpath.replace("///", "//").replace("//", "/descendant::")
    segments = [s for s in clean_xpath.split('/') if s]
    
    steps = []
    for seg in segments:
        depth = 1
        if seg.startswith("descendant::"):
            depth = 20
            seg = seg.replace("descendant::", "")
            
        type_match = re.match(r"^([a-zA-Z]+)", seg)
        if not type_match: continue
        ctype_name = type_match.group(1)
        ctype_name = ctype_name + "Control" if not ctype_name.endswith("Control") else ctype_name
        
        attrs = {}
        # 兼容以下两种写法：
        # 1) Window[@ClassName='Notepad'][@ProcessName='Notepad.exe']
        # 2) Window[@ClassName='Notepad' and @ProcessName='Notepad.exe']
        for attr_match in re.finditer(r"@([a-zA-Z0-9_]+)\s*=\s*(['\"])(.*?)\2", seg):
            attrs[attr_match.group(1)] = _unescape_xpath_string(attr_match.group(3))
            
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

    if DEBUG:
        _debug(f"[*] 解析得到 {len(steps)} 个 steps")
        for idx, st in enumerate(steps, start=1):
            _debug(f"    - step {idx}: type={st['type_name']} depth={st['depth']} index={st['index']} attrs={st['attrs']} raw={st['raw']}")

    # =========================================================
    # 优先处理第 0 段的 ProcessName：同进程多窗口时逐个试探，避免锁错窗口
    # =========================================================
    if steps and "ProcessName" in steps[0]["attrs"]:
        pname = (steps[0]["attrs"].get("ProcessName") or "").lower()
        if not pname:
            return None

        candidates = []
        try:
            for child in current_node.GetChildren():
                try:
                    if not child.ProcessId:
                        continue

                    # 优先 psutil（若可用），否则用项目自带的 Win32 PID->name
                    if psutil:
                        try:
                            child_pname = psutil.Process(child.ProcessId).name()
                        except Exception:
                            child_pname = None
                    else:
                        child_pname = get_process_name(child.ProcessId)

                    if child_pname and child_pname.lower() == pname:
                        candidates.append(child)
                except Exception:
                    pass
        except Exception:
            candidates = []

        if DEBUG:
            _debug(f" -> [特权通道] 命中 {len(candidates)} 个候选窗口（进程 {pname}），开始逐个试探...")
            for k, c in enumerate(candidates, start=1):
                try:
                    _debug(
                        f"    - cand {k}: pid={c.ProcessId} hwnd={getattr(c, 'NativeWindowHandle', None)} "
                        f"type={c.ControlTypeName} class={c.ClassName!r} name={c.Name!r}"
                    )
                except Exception:
                    _debug(f"    - cand {k}: <无法读取候选窗口属性>")

        if not candidates:
            return None

        # 把第 0 段的 ProcessName 去掉，保留其它约束（ClassName/Name/AutomationId）
        first_step = dict(steps[0])
        first_attrs = dict(first_step["attrs"])
        first_attrs.pop("ProcessName", None)
        first_step["attrs"] = first_attrs

        for cand in candidates:
            # 如果第 0 段就是 Window，并且其它约束匹配，则直接从下一段开始
            if first_step["type_name"] == "WindowControl" and _matches_attrs(cand, first_attrs):
                if DEBUG:
                    _debug("    [试探] cand 匹配第 0 段 Window 约束，直接从 step 2 开始。")
                result = _locate_from_node(cand, steps, 1, start_time, timeout)
            else:
                # 否则从 cand 作为起点，先正常执行第 0 段（去掉 ProcessName 后）
                tmp_steps = [first_step] + steps[1:]
                if DEBUG:
                    _debug("    [试探] cand 不满足第 0 段 Window 约束（或第 0 段非 Window），从 step 1 重新寻路。")
                result = _locate_from_node(cand, tmp_steps, 0, start_time, timeout)

            if result:
                if DEBUG:
                    _debug("    [+] 试探成功：已找到目标元素。")
                return result

            if DEBUG:
                _debug("    [-] 试探失败：该候选窗口无法走通整条 XPath。")

        return None
    
    for i, step in enumerate(steps):
        if time.time() - start_time > timeout:
            if DEBUG:
                _debug(f"[-] 寻址超时！折戟于第 {i+1} 层。")
            return None
            
        # 第 0 段 ProcessName 已在上方专门处理（逐窗口试探）

        # 常规 UIA 寻路
        search_kwargs = {
            "searchFromControl": current_node,
            "searchDepth": step["depth"],
            "foundIndex": step["index"]
        }
        
        if hasattr(auto.ControlType, step["type_name"]):
            search_kwargs["ControlType"] = getattr(auto.ControlType, step["type_name"])
            
        if "ClassName" in step["attrs"]:
            if step["type_name"] == "DocumentControl" and "Chrome" in step["attrs"]["ClassName"]:
                pass 
            else:
                search_kwargs["ClassName"] = step["attrs"]["ClassName"]
                
        if "Name" in step["attrs"]:
            search_kwargs["Name"] = step["attrs"]["Name"]

        if "AutomationId" in step["attrs"]:
            search_kwargs["AutomationId"] = step["attrs"]["AutomationId"]
            
        if DEBUG:
            _debug(f" -> 逐层破解 [{i+1}/{len(steps)}]: 检索 {step['raw']} ...")
        
        try:
            next_node = auto.Control(**search_kwargs)
            
            if not next_node.Exists(3.0, 0.2):
                if step["type_name"] == "DocumentControl" and current_node.NativeWindowHandle:
                    if DEBUG:
                        _debug(f"    [!] 检测到 UIA 树虚假断裂，启动 HWND 底层穿透...")
                    docs = bridge_to_renderer(current_node.NativeWindowHandle)
                    target_idx = step["index"] - 1
                    if docs and target_idx < len(docs):
                        if DEBUG:
                            _debug(f"    [+] 穿透成功！强行捕获到底层渲染画布！")
                        current_node = docs[target_idx]
                        continue
                        
                if DEBUG:
                    _debug(f"[-] 坐标反推失败：UIA 树在 {step['raw']} 处彻底断裂。")
                return None
                
            current_node = next_node
        except Exception as e:
            if DEBUG:
                _debug(f"[-] 寻址发生崩溃（step={step['raw']}）: {e}")
            return None

    return current_node