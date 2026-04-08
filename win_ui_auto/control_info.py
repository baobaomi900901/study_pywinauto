# control_info.py
import uiautomation as auto
import json
import time
from process_utils import get_process_name   # 修改此处：去掉开头的点

def is_highlight_window(ctrl, current_pid):
    try:
        return (ctrl.ClassName == "TkChild" and ctrl.ProcessId == current_pid)
    except:
        return False

def is_same_control(ctrl1, ctrl2):
    if ctrl1 is None or ctrl2 is None:
        return False
    try:
        if ctrl1.AutomationId and ctrl2.AutomationId:
            return ctrl1.AutomationId == ctrl2.AutomationId
        if (ctrl1.ControlTypeName == ctrl2.ControlTypeName and
            ctrl1.ClassName == ctrl2.ClassName and ctrl1.Name == ctrl2.Name):
            r1 = ctrl1.BoundingRectangle
            r2 = ctrl2.BoundingRectangle
            if r1 and r2:
                return (r1.left == r2.left and r1.top == r2.top and
                        r1.width() == r2.width() and r1.height() == r2.height())
        return False
    except:
        return ctrl1 == ctrl2

def get_deepest_control(x, y, current_pid):
    try:
        ctrl = auto.ControlFromPoint(x, y)
        if not ctrl or is_highlight_window(ctrl, current_pid):
            return None
        while True:
            children = ctrl.GetChildren()
            found_deeper = False
            for child in children:
                if is_highlight_window(child, current_pid):
                    continue
                rect = child.BoundingRectangle
                if rect and rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                    ctrl = child
                    found_deeper = True
                    break
            if not found_deeper:
                break
        return ctrl
    except Exception:
        return None

def get_control_info(control, x, y, current_pid):
    try:
        rect = control.BoundingRectangle
        if not rect:
            return None
        x0, y0, w, h = rect.left, rect.top, rect.width(), rect.height()

        try:
            value_pattern = control.GetValuePattern()
            value = value_pattern.Value if value_pattern else ""
        except:
            value = ""

        try:
            help_text = control.HelpText or ""
        except:
            help_text = ""

        try:
            is_password = getattr(control, 'IsPassword', False)
        except:
            is_password = False

        ctrl_type = control.ControlTypeName or ""

        my_index = 0
        my_same_type_index = 0
        try:
            my_parent = control.GetParentControl()
            if my_parent:
                siblings = my_parent.GetChildren()
                same_type_count = 0
                for i, sibling in enumerate(siblings):
                    if is_same_control(sibling, control):
                        my_index = i
                    if sibling.ControlTypeName == ctrl_type:
                        if is_same_control(sibling, control):
                            my_same_type_index = same_type_count
                        same_type_count += 1
        except:
            pass

        parent_chain = []
        app_info = None
        node = control.GetParentControl()
        while node and not is_highlight_window(node, current_pid):
            node_type = node.ControlTypeName or ""
            node_index = 0
            node_same_type_index = 0
            try:
                grandparent = node.GetParentControl()
                if grandparent:
                    siblings = grandparent.GetChildren()
                    same_type_count = 0
                    for i, sibling in enumerate(siblings):
                        if is_same_control(sibling, node):
                            node_index = i
                        if sibling.ControlTypeName == node_type:
                            if is_same_control(sibling, node):
                                node_same_type_index = same_type_count
                            same_type_count += 1
            except:
                pass

            node_info = {
                "ControlType": node_type,
                "ClassName": node.ClassName or "",
                "index": node_index,
                "same_type_index": node_same_type_index
            }
            if node_type == "PaneControl" and node.ClassName == "#32769":
                node_info["is_desktop"] = True
            if node_type == "WindowControl" and app_info is None:
                node_info["is_app"] = True
                pid = node.ProcessId
                if pid:
                    proc_name = get_process_name(pid)
                    app_info = {"pid": pid, "name": proc_name or "未知"}
            parent_chain.insert(0, node_info)
            node = node.GetParentControl()

        info = {
            "ControlType": ctrl_type,
            "ClassName": control.ClassName or "",
            "Name": control.Name or "",
            "position": [x0, y0, w, h],
            "Value": value,
            "HelpText": help_text,
            "IsPassword": is_password,
            "index": my_index,
            "same_type_index": my_same_type_index,
            "parent": parent_chain
        }
        if app_info:
            info["application"] = app_info
        return info
    except Exception:
        return None

def print_control_info(info, last_printed_id, last_print_time, interval=0.1):
    if not info:
        return last_printed_id, last_print_time
    pos = info["position"]
    ctrl_id = (info["ControlType"], info["ClassName"], info["Name"],
               info.get("index"), info.get("same_type_index"),
               round(pos[0] / 5) * 5, round(pos[1] / 5) * 5)
    now = time.time()
    if ctrl_id != last_printed_id or now - last_print_time > interval:
        print(f"\n[UI 信息]\n{json.dumps(info, ensure_ascii=False, indent=2)}")
        return ctrl_id, now
    return last_printed_id, last_print_time