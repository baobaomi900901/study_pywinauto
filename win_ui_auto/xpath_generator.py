# win_ui_auto/xpath_generator.py
USE_SHORT_XPATH = True   # 设置为 False 可恢复原长名称

def generate_xpath(control_info, parent_chain):
    filtered_parents = [p for p in parent_chain if not p.get("is_desktop", False)]
    segments = []
    for parent in filtered_parents:
        seg = _make_segment(parent["ControlType"], parent.get("ClassName"),
                            parent.get("index"), parent.get("same_type_index"))
        segments.append(seg)
    current_seg = _make_segment(control_info["ControlType"], control_info.get("ClassName"),
                                control_info.get("index"), control_info.get("same_type_index"),
                                name=control_info.get("Name"))
    segments.append(current_seg)
    if not segments:
        return ""
    return "//" + "/".join(segments)

def _make_segment(control_type, class_name=None, index=None, same_type_index=None, name=None):
    seg = _short_type(control_type)
    attributes = []
    position = None

    if name and name.strip():
        attributes.append(f"@Name='{_escape_xpath_string(name)}'")
    else:
        if class_name:
            attributes.append(f"@ClassName='{_escape_xpath_string(class_name)}'")
        if same_type_index is not None:
            position = same_type_index + 1

    if attributes:
        seg += f"[{' and '.join(attributes)}]"
    if position is not None:
        seg += f"[{position}]"
    return seg

def _short_type(control_type):
    if USE_SHORT_XPATH and control_type.endswith("Control"):
        return control_type[:-7]
    return control_type

def _escape_xpath_string(s):
    return s.replace("'", "&apos;")