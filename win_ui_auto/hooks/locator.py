# win_ui_auto/hooks/locator.py
import sys
import time
import re
import fnmatch
from collections import deque
import uiautomation as auto
import ctypes
from ctypes import wintypes

try:
    import psutil
except ImportError:
    psutil = None

from constants import DEBUG
from process_utils import get_process_name, get_window_class_name, hwnd_c_void_p
from xpath_generator import CAPTURE_OVERLAY_CLASS

# 单 '/' 解析为 depth=1 时仅匹配直接子级；WinUI 等常有中间层，Exists 失败时放宽到此深度再试
SHALLOW_STEP_FALLBACK_SEARCH_DEPTH = 30

# FindFirst/Exists 在 WinUI 3 菜单栏等节点上可能与子树真实结构不一致；DFS 上限防止卡死
DFS_FALLBACK_MAX_VISITS = 8000
# 仅对这些类型做 DFS（避免「真不存在」时在整棵子树上扫满上限）
_DFS_FALLBACK_CONTROL_TYPES = frozenset(
    {
        "MenuBarControl",
        "MenuControl",
        "ToolBarControl",
    }
)


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

def _is_glob_pattern(value: str) -> bool:
    if not value:
        return False
    return "*" in value or "?" in value


def _process_name_matches(pattern: str, actual_exe: str) -> bool:
    """进程名（如 Notepad.exe）：无通配时大小写不敏感精确匹配；含 * ? 时用 fnmatch，同样按小写比较。"""
    if not pattern or not actual_exe:
        return False
    p = pattern.strip().lower()
    a = actual_exe.strip().lower()
    if _is_glob_pattern(p):
        return fnmatch.fnmatch(a, p)
    return a == p


def _control_matches_step_attrs(ctrl, attrs: dict) -> bool:
    """Name / ClassName / AutomationId：无通配则精确相等，含 * ? 则用 fnmatch（ProcessName 在特权通道单独匹配）。"""
    for key, pattern in (attrs or {}).items():
        if key == "ProcessName":
            continue
        if key not in ("ClassName", "Name", "AutomationId"):
            continue
        try:
            if key == "ClassName":
                actual = ctrl.ClassName or ""
            elif key == "Name":
                actual = ctrl.Name or ""
            else:
                actual = ctrl.AutomationId or ""
        except Exception:
            return False
        if _is_glob_pattern(pattern):
            if not fnmatch.fnmatch(actual, pattern):
                return False
        else:
            if actual != pattern:
                return False
    return True


def _matches_attrs(ctrl, attrs: dict) -> bool:
    """在已找到的 ctrl 上校验 attrs（用于 ProcessName 锚点后不丢约束）；支持通配。"""
    return _control_matches_step_attrs(ctrl, attrs)


def _step_attrs_need_glob_scan(step: dict) -> bool:
    for k, v in (step.get("attrs") or {}).items():
        if k == "ProcessName":
            continue
        if k in ("ClassName", "Name", "AutomationId") and _is_glob_pattern(v):
            return True
    return False


def _dfs_nth_match_subtree(root, step: dict, start_time: float, timeout: float):
    """
    在 root 的子树中按前序（与 GetChildren 顺序一致）找第 index 个匹配
    ControlType + attrs 的控件。用于 IUIAutomation::Find 漏检 MSAA/WinUI 混合节点的情况。
    """
    want = max(1, int(step.get("index") or 1))
    typ = step.get("type_name") or ""
    attrs = step.get("attrs") or {}
    hits = []
    visits = [0]

    def visit(node):
        if time.time() - start_time > timeout:
            return
        if visits[0] >= DFS_FALLBACK_MAX_VISITS:
            return
        visits[0] += 1
        try:
            cname = node.ControlTypeName
        except Exception:
            return
        if cname == typ and _control_matches_step_attrs(node, attrs):
            hits.append(node)
            if len(hits) >= want:
                return
        try:
            children = node.GetChildren()
        except Exception:
            return
        if not children:
            return
        for ch in children:
            if len(hits) >= want or time.time() - start_time > timeout:
                return
            visit(ch)

    try:
        visit(root)
    except Exception:
        return None
    if len(hits) >= want:
        return hits[want - 1]
    return None


def _runtime_id_tuple(ctrl):
    try:
        rid = ctrl.GetRuntimeId()
        return tuple(rid) if rid is not None else None
    except Exception:
        return None


def _is_descendant_under_anchor(node, anchor):
    """沿 GetParent 能否走到 anchor（用于确认 ControlFromPoint 命中的菜单栏属于当前 XPath 锚点子树）。"""
    aid = _runtime_id_tuple(anchor)
    p = node
    for _ in range(72):
        try:
            p = p.GetParentControl()
        except Exception:
            return False
        if p is None:
            return False
        if aid is not None:
            try:
                if _runtime_id_tuple(p) == aid:
                    return True
            except Exception:
                pass
        else:
            try:
                if p == anchor:
                    return True
            except Exception:
                pass
    return False


def _menu_geom_inside_anchor(mb, anchor):
    """父链断裂时，用屏幕几何判断菜单栏是否落在锚点 Pane 的矩形内（与探查父链一致）。"""
    try:
        ra = anchor.BoundingRectangle
        rm = mb.BoundingRectangle
        if not ra or not rm or ra.width() <= 0 or rm.width() <= 0:
            return False
        cx = rm.left + rm.width() // 2
        cy = rm.top + rm.height() // 2
        return ra.left <= cx <= ra.right and ra.top <= cy <= ra.bottom
    except Exception:
        return False


def _same_top_window_as_anchor(menubar, anchor):
    """
    WinUI：菜单栏与 InputSite 在 UIA 父链上可能不相连，但同属一个 Notepad 顶层窗口。
    在严格「锚点后代」失败时，用「同一 Window 节点 + 同进程」接受命中。
    """
    try:
        w_mb = _ancestor_window_control(menubar)
        w_an = _ancestor_window_control(anchor)
        if w_mb is None or w_an is None:
            return False
        rmb, ran = _runtime_id_tuple(w_mb), _runtime_id_tuple(w_an)
        same_win = False
        if rmb is not None and ran is not None and rmb == ran:
            same_win = True
        elif rmb is not None and ran is not None:
            return False
        if not same_win:
            try:
                hw = int(w_mb.NativeWindowHandle or 0)
                ha = int(w_an.NativeWindowHandle or 0)
                if hw and ha and hw == ha:
                    same_win = True
            except Exception:
                pass
        if not same_win:
            try:
                if (w_mb.ClassName or "") == (w_an.ClassName or "") and (
                    (w_mb.Name or "") == (w_an.Name or "")
                ):
                    same_win = True
            except Exception:
                pass
        if not same_win:
            return False
        pmb, pan = menubar.ProcessId, anchor.ProcessId
        if pmb and pan and int(pmb) != int(pan):
            return False
        return True
    except Exception:
        return False


def _walk_up_to_menubar(start):
    """从 ControlFromPoint 命中节点沿父链向上找 MenuBarControl（点在「文件」等菜单项上时常用）。"""
    p = start
    for _ in range(20):
        if p is None:
            return None
        try:
            if p.ControlTypeName == "MenuBarControl":
                return p
        except Exception:
            pass
        try:
            p = p.GetParentControl()
        except Exception:
            break
    return None


def _ancestor_window_control(start):
    p = start
    for _ in range(48):
        if p is None:
            return None
        try:
            if p.ControlTypeName == "WindowControl":
                return p
        except Exception:
            pass
        try:
            p = p.GetParentControl()
        except Exception:
            break
    return None


def _menubar_candidates_from_point(hit):
    """从一次点命中解析可能的 MenuBar 控件（自身或祖先链上的 MenuBar）。"""
    if not hit:
        return []
    seen = set()
    out = []

    def _add(n):
        if not n:
            return
        key = _runtime_id_tuple(n)
        if key is None:
            key = ("id", id(n))
        if key in seen:
            return
        seen.add(key)
        out.append(n)

    try:
        if hit.ControlTypeName == "MenuBarControl":
            _add(hit)
    except Exception:
        pass
    up = _walk_up_to_menubar(hit)
    if up is not None:
        _add(up)
    return out


def _menubar_by_controlpoint_under_anchor(cur, step, start_time, timeout):
    """
    WinUI 3 记事本等：MenuBar 常经 MSAA 暴露，ControlView 子树遍历与 Find 均不见；
    与探针一致用屏幕坐标命中；命中多为菜单项/标题，需向上找 MenuBarControl。
    校验：优先要求为 anchor 的后代；否则同一顶层窗口且同进程（InputSite 与菜单 UIA 链常脱钩）。
    """
    if step.get("type_name") != "MenuBarControl":
        return None
    attrs = step.get("attrs") or {}
    want = max(1, int(step.get("index") or 1))
    win = _ancestor_window_control(cur) or cur
    try:
        r = win.BoundingRectangle
    except Exception:
        return None
    if not r or r.width() <= 0 or r.height() <= 0:
        return None
    hits_strict = []
    hits_loose = []
    seen = set()

    def _try_add(mb, strict_ok):
        nonlocal hits_strict, hits_loose
        if not mb:
            return
        if not _control_matches_step_attrs(mb, attrs):
            return
        rid = _runtime_id_tuple(mb)
        key = rid if rid is not None else ("id", id(mb))
        if key in seen:
            return
        seen.add(key)
        if strict_ok:
            hits_strict.append(mb)
        else:
            hits_loose.append(mb)

    # 含 Win11 带标签栏时菜单条偏下的情况
    fracs_y = (0.028, 0.038, 0.05, 0.065, 0.08, 0.1, 0.12, 0.14, 0.17, 0.2, 0.24, 0.28)
    fracs_x = (0.12, 0.22, 0.32, 0.42, 0.5, 0.58, 0.68, 0.78, 0.88)
    for fy in fracs_y:
        if time.time() - start_time > timeout:
            break
        cy = int(r.top + max(2, min(r.height() * fy, r.height() - 2)))
        for fx in fracs_x:
            if time.time() - start_time > timeout:
                break
            cx = int(r.left + r.width() * fx)
            try:
                raw_hit = auto.ControlFromPoint(cx, cy)
            except OverflowError:
                try:
                    raw_hit = auto.ControlFromPoint2(cx, cy)
                except Exception:
                    raw_hit = None
            except Exception:
                raw_hit = None
            for mb in _menubar_candidates_from_point(raw_hit):
                if _is_descendant_under_anchor(mb, cur) or _menu_geom_inside_anchor(
                    mb, cur
                ):
                    _try_add(mb, True)
                elif _same_top_window_as_anchor(mb, cur):
                    _try_add(mb, False)
            pool = hits_strict if len(hits_strict) >= want else hits_strict + hits_loose
            if len(pool) >= want:
                return pool[want - 1]
    pool = hits_strict if len(hits_strict) >= want else hits_strict + hits_loose
    if len(pool) >= want:
        return pool[want - 1]

    # 点阵仍扫不到时：从顶层窗口做一次浅 BFS（Find 子树与真实控件脱节时仍可见 MenuBar）
    try:
        dq = deque([(win, 0)])
        bfs_visits = 0
        while dq and bfs_visits < 3000:
            if time.time() - start_time > timeout:
                break
            node, depth = dq.popleft()
            bfs_visits += 1
            if depth > 14:
                continue
            try:
                if node.ControlTypeName == "MenuBarControl":
                    if _is_descendant_under_anchor(node, cur) or _menu_geom_inside_anchor(
                        node, cur
                    ):
                        _try_add(node, True)
                    elif _same_top_window_as_anchor(node, cur):
                        _try_add(node, False)
                    pool = (
                        hits_strict
                        if len(hits_strict) >= want
                        else hits_strict + hits_loose
                    )
                    if len(pool) >= want:
                        return pool[want - 1]
            except Exception:
                pass
            try:
                for ch in node.GetChildren() or []:
                    dq.append((ch, depth + 1))
            except Exception:
                pass
    except Exception:
        pass

    pool = hits_strict if len(hits_strict) >= want else hits_strict + hits_loose
    if len(pool) >= want:
        return pool[want - 1]
    return None


def _build_uia_kwargs(current_node, step: dict, found_index: int, exclude_glob_attrs: bool) -> dict:
    search_kwargs = {
        "searchFromControl": current_node,
        "searchDepth": step["depth"],
        "foundIndex": found_index,
    }
    if hasattr(auto.ControlType, step["type_name"]):
        search_kwargs["ControlType"] = getattr(auto.ControlType, step["type_name"])
    attrs = step.get("attrs") or {}
    if "ClassName" in attrs:
        v = attrs["ClassName"]
        if exclude_glob_attrs and _is_glob_pattern(v):
            pass
        elif step["type_name"] == "DocumentControl" and "Chrome" in v:
            pass
        else:
            search_kwargs["ClassName"] = v
    if "Name" in attrs:
        v = attrs["Name"]
        if not (exclude_glob_attrs and _is_glob_pattern(v)):
            search_kwargs["Name"] = v
    if "AutomationId" in attrs:
        v = attrs["AutomationId"]
        if not (exclude_glob_attrs and _is_glob_pattern(v)):
            search_kwargs["AutomationId"] = v
    return search_kwargs


def _resolve_one_step(current_node, step, start_time, timeout, max_scan=400):
    """执行单段 XPath：支持属性通配；保留 Chrome Document 桥接重试逻辑。"""
    cur = current_node
    while True:
        if time.time() - start_time > timeout:
            return None

        if _step_attrs_need_glob_scan(step):
            if DEBUG:
                _debug(f" -> 逐层破解（属性通配）: 检索 {step['raw']} ...")
            want = max(1, int(step.get("index") or 1))
            matched = []
            for k in range(1, max_scan):
                if time.time() - start_time > timeout:
                    break
                kwargs = _build_uia_kwargs(cur, step, k, exclude_glob_attrs=True)
                try:
                    c = auto.Control(**kwargs)
                except Exception:
                    break
                ok = c.Exists(0.4, 0.12)
                if not ok and int(step.get("depth") or 1) <= 1:
                    try:
                        c = auto.Control(
                            **{**kwargs, "searchDepth": SHALLOW_STEP_FALLBACK_SEARCH_DEPTH}
                        )
                        ok = c.Exists(0.4, 0.12)
                    except Exception:
                        ok = False
                if not ok:
                    break
                if _control_matches_step_attrs(c, step["attrs"]):
                    matched.append(c)
                    if len(matched) >= want:
                        return c
            if step.get("type_name") in _DFS_FALLBACK_CONTROL_TYPES:
                dfs_hit = _dfs_nth_match_subtree(cur, step, start_time, timeout)
                if dfs_hit is not None:
                    if DEBUG:
                        _debug(
                            f"    [+] 通配扫描未果，子树 DFS 回退成功：{step['raw']}"
                        )
                    return dfs_hit
            pt_hit = _menubar_by_controlpoint_under_anchor(cur, step, start_time, timeout)
            if pt_hit is not None:
                if DEBUG:
                    _debug(
                        f"    [+] 通配扫描未果，ControlFromPoint 命中 MenuBar：{step['raw']}"
                    )
                return pt_hit
            return None

        if DEBUG:
            _debug(f" -> 逐层破解: 检索 {step['raw']} ...")

        search_kwargs = _build_uia_kwargs(cur, step, step["index"], exclude_glob_attrs=False)
        try:
            next_node = auto.Control(**search_kwargs)
            if next_node.Exists(3.0, 0.2):
                return next_node
            if int(step.get("depth") or 1) <= 1:
                sk_deep = {
                    **search_kwargs,
                    "searchDepth": SHALLOW_STEP_FALLBACK_SEARCH_DEPTH,
                }
                try:
                    next_relaxed = auto.Control(**sk_deep)
                    if next_relaxed.Exists(3.0, 0.2):
                        if DEBUG:
                            _debug(
                                f"    [+] depth=1 未命中，已用 searchDepth="
                                f"{SHALLOW_STEP_FALLBACK_SEARCH_DEPTH} 回退：{step['raw']}"
                            )
                        return next_relaxed
                except Exception:
                    pass
            if step.get("type_name") in _DFS_FALLBACK_CONTROL_TYPES:
                dfs_hit = _dfs_nth_match_subtree(cur, step, start_time, timeout)
                if dfs_hit is not None:
                    if DEBUG:
                        _debug(
                            f"    [+] Find/Exists 未命中，子树 DFS 回退成功：{step['raw']}"
                        )
                    return dfs_hit
            pt_hit = _menubar_by_controlpoint_under_anchor(cur, step, start_time, timeout)
            if pt_hit is not None:
                if DEBUG:
                    _debug(
                        f"    [+] Find/DFS 未命中 MenuBar，已用 ControlFromPoint 回退：{step['raw']}"
                    )
                return pt_hit
            if DEBUG:
                _debug(f"    [-] Exists 失败：{step['raw']}")
            if step["type_name"] == "DocumentControl" and cur.NativeWindowHandle:
                if DEBUG:
                    _debug(f"    [!] 检测到 UIA 树虚假断裂，启动 HWND 底层穿透...")
                docs = bridge_to_renderer(cur.NativeWindowHandle)
                target_idx = step["index"] - 1
                if docs and target_idx < len(docs):
                    if DEBUG:
                        _debug(f"    [+] 穿透成功！强行捕获到底层渲染画布！")
                    cur = docs[target_idx]
                    continue
            return None
        except Exception as e:
            if DEBUG:
                _debug(f"[-] 寻址发生崩溃（step={step['raw']}）: {e}")
            return None


def _locate_from_node(start_node, steps, start_index, start_time, timeout, end_index_exclusive=None):
    """从指定 start_node 开始执行 steps[start_index : end_index_exclusive]（不再处理 ProcessName 特权通道）。"""
    current_node = start_node
    if end_index_exclusive is None:
        end_index_exclusive = len(steps)

    for j in range(start_index, end_index_exclusive):
        step = steps[j]
        if time.time() - start_time > timeout:
            if DEBUG:
                print(f"[-] 寻址超时！折戟于第 {j+1} 层。")
            return None
        nxt = _resolve_one_step(current_node, step, start_time, timeout)
        if nxt is None:
            if DEBUG:
                _debug(f"[-] 坐标反推失败：UIA 树在 {step['raw']} 处彻底断裂。")
            return None
        current_node = nxt

    return current_node


def _enumerate_matches_at_last_step(anchor, last_step, start_time, timeout, max_matches=200):
    """在已定位的锚点下枚举最后一档：无通配时按 foundIndex；有通配时扫描后 fnmatch 过滤。"""
    out = []
    if _step_attrs_need_glob_scan(last_step):
        for k in range(1, max_matches + 1):
            if time.time() - start_time > timeout:
                break
            kwargs = _build_uia_kwargs(anchor, last_step, k, exclude_glob_attrs=True)
            try:
                c = auto.Control(**kwargs)
            except Exception:
                break
            if not c.Exists(0.45, 0.1):
                break
            if _control_matches_step_attrs(c, last_step["attrs"]):
                out.append(c)
        if not out and last_step.get("type_name") == "MenuBarControl":
            mb = _menubar_by_controlpoint_under_anchor(
                anchor, last_step, start_time, timeout
            )
            if mb is not None:
                if DEBUG:
                    _debug(
                        "    [+] 最后一档枚举：Find 未命中 MenuBar，已用 ControlFromPoint 回退"
                    )
                return [mb]
        return out

    for k in range(1, max_matches + 1):
        if time.time() - start_time > timeout:
            break
        kwargs = _build_uia_kwargs(anchor, last_step, k, exclude_glob_attrs=False)
        try:
            c = auto.Control(**kwargs)
        except Exception:
            break
        ok = c.Exists(0.45, 0.1)
        if not ok and int(last_step.get("depth") or 1) <= 1:
            try:
                c = auto.Control(
                    **{**kwargs, "searchDepth": SHALLOW_STEP_FALLBACK_SEARCH_DEPTH}
                )
                ok = c.Exists(0.45, 0.1)
            except Exception:
                ok = False
        if not ok:
            break
        out.append(c)
    if not out and last_step.get("type_name") == "MenuBarControl":
        mb = _menubar_by_controlpoint_under_anchor(
            anchor, last_step, start_time, timeout
        )
        if mb is not None:
            if DEBUG:
                _debug(
                    "    [+] 最后一档枚举：Find 未命中 MenuBar，已用 ControlFromPoint 回退"
                )
            return [mb]
    return out


def _parse_xpath_steps(xpath):
    """解析 XPath 为 steps 列表；失败或空路径返回 []。"""
    clean_xpath = xpath.replace("///", "//").replace("//", "/descendant::")
    segments = [s for s in clean_xpath.split("/") if s]
    steps = []
    for seg in segments:
        depth = 1
        if seg.startswith("descendant::"):
            depth = 20
            seg = seg.replace("descendant::", "")
        type_match = re.match(r"^([a-zA-Z]+)", seg)
        if not type_match:
            continue
        ctype_name = type_match.group(1)
        ctype_name = ctype_name + "Control" if not ctype_name.endswith("Control") else ctype_name
        attrs = {}
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
            "depth": depth,
        })
    return steps


def locate_all_by_xpath(xpath, timeout=10.0, max_matches=200):
    """
    返回满足整条 XPath 的最后一档约束的全部控件（foundIndex 1..N）。
    用于同一 AutomationId/Name 下多实例时批量高亮等场景。
    """
    if DEBUG:
        _debug(f"[*] XPath 全量匹配（最后一档枚举）...")

    steps = _parse_xpath_steps(xpath)
    if not steps:
        return []

    if any((s.get("attrs") or {}).get("ClassName") == CAPTURE_OVERLAY_CLASS for s in steps):
        print(
            "提示: XPath 指向本工具探测遮罩 (ClassName=WinUiAuto_CaptureOverlay)。",
            file=sys.stderr,
        )
        return []

    start_time = time.time()
    current_node = auto.GetRootControl()

    if DEBUG:
        _debug(f"[*] 解析得到 {len(steps)} 个 steps（全量模式）")

    # ProcessName 特权通道：与 locate_by_xpath 一致，找到锚点后枚举最后一档
    if steps and "ProcessName" in steps[0]["attrs"]:
        pname_raw = (steps[0]["attrs"].get("ProcessName") or "").strip()
        if not pname_raw:
            return []

        candidates = []
        try:
            for child in current_node.GetChildren():
                try:
                    if not child.ProcessId:
                        continue
                    if psutil:
                        try:
                            child_pname = psutil.Process(child.ProcessId).name()
                        except Exception:
                            child_pname = None
                    else:
                        child_pname = get_process_name(child.ProcessId)
                    if child_pname and _process_name_matches(pname_raw, child_pname):
                        candidates.append(child)
                except Exception:
                    pass
        except Exception:
            candidates = []

        if not candidates:
            return []

        first_step = dict(steps[0])
        first_attrs = dict(first_step["attrs"])
        first_attrs.pop("ProcessName", None)
        first_step["attrs"] = first_attrs

        # 仅一段且带 ProcessName：候选已是同进程顶层控件，按首段属性过滤（多实例窗口）
        if len(steps) == 1:
            out = []
            for cand in candidates:
                if first_step["type_name"] == "WindowControl" and _matches_attrs(cand, first_attrs):
                    out.append(cand)
                else:
                    r = _locate_from_node(cand, [first_step], 0, start_time, timeout, 1)
                    if r:
                        out.append(r)
            return out

        for cand in candidates:
            anchor = None
            if first_step["type_name"] == "WindowControl" and _matches_attrs(cand, first_attrs):
                anchor = _locate_from_node(cand, steps, 1, start_time, timeout, len(steps) - 1)
            else:
                tmp_steps = [first_step] + steps[1:]
                anchor = _locate_from_node(cand, tmp_steps, 0, start_time, timeout, len(tmp_steps) - 1)

            if not anchor:
                continue
            found = _enumerate_matches_at_last_step(anchor, steps[-1], start_time, timeout, max_matches)
            if found:
                return found
        return []

    # 常规路径
    if len(steps) == 1:
        anchor = current_node
        return _enumerate_matches_at_last_step(anchor, steps[0], start_time, timeout, max_matches)

    anchor = _locate_from_node(current_node, steps, 0, start_time, timeout, len(steps) - 1)
    if not anchor:
        return []
    return _enumerate_matches_at_last_step(anchor, steps[-1], start_time, timeout, max_matches)

def bridge_to_renderer(top_hwnd):
    """HWND 底层穿透：寻找真实的渲染窗口，绕过 CEF 的 UIA 树断层"""
    hwnds = []
    user32 = ctypes.windll.user32
    
    def enum_child_proc(h, lParam):
        cn = get_window_class_name(h)
        if "Chrome_RenderWidgetHostHWND" in cn or "Render" in cn:
            try:
                hv = int(ctypes.cast(h, ctypes.c_void_p).value or 0)
            except Exception:
                hv = int(h) if isinstance(h, int) else 0
            if hv:
                hwnds.append(hv)
        return True

    EnumChildProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, wintypes.LPARAM)
    user32.EnumChildWindows(
        hwnd_c_void_p(top_hwnd), EnumChildProcType(enum_child_proc), 0
    )
    
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

    steps = _parse_xpath_steps(xpath)

    if any((s.get("attrs") or {}).get("ClassName") == CAPTURE_OVERLAY_CLASS for s in steps):
        print(
            "提示: XPath 指向本工具探测遮罩 (ClassName=WinUiAuto_CaptureOverlay)。"
            "该窗口仅在「--find 探查模式」运行期间存在，单独执行 --get 时桌面上没有此元素。"
            "请对目标应用上的控件重新抓取 XPath；抓取时避免点在透明遮罩上（未按 Ctrl 时遮罩不拦截鼠标）。",
            file=sys.stderr,
        )
        return None

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
        pname_raw = (steps[0]["attrs"].get("ProcessName") or "").strip()
        if not pname_raw:
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

                    if child_pname and _process_name_matches(pname_raw, child_pname):
                        candidates.append(child)
                except Exception:
                    pass
        except Exception:
            candidates = []

        if DEBUG:
            _debug(f" -> [特权通道] 命中 {len(candidates)} 个候选窗口（进程 {pname_raw!r}），开始逐个试探...")
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

    # 常规 UIA 寻路（与 _locate_from_node 共用，含属性通配）
    return _locate_from_node(current_node, steps, 0, start_time, timeout)