# win_ui_auto/xpath_generator.py
USE_SHORT_XPATH = True
OMIT_DEFAULT_INDEX = True 

def generate_xpath(control_info, parent_chain):
    filtered_parents = [p for p in parent_chain if not p.get("is_desktop", False)]
    all_nodes = filtered_parents + [control_info]
    segments = []
    
    # 1. 寻找最佳的"应用外壳"起点
    start_index = 0
    for i in range(len(all_nodes)-1, -1, -1):
        node = all_nodes[i]
        name = node.get("Name", "")
        # 必须带有明确特征（类名或名字）且属于应用容器
        has_identity = bool(name.strip() or node.get("ClassName", "").strip())
        is_shell = node.get("is_app", False) or "Chrome_WidgetWin_1" in node.get("ClassName", "")
        
        if has_identity and is_shell:
            start_index = i
            break
            
    # 2. 从探针的原始数据中提取应用进程名
    app_name = control_info.get("application", {}).get("name", "")
    
    # 3. 生成路径段
    for i in range(start_index, len(all_nodes)):
        node = all_nodes[i]
        # 只在第一层打上进程基因锁
        p_name = app_name if i == start_index else None
        
        seg = _make_segment(
            control_type=node.get("ControlType", ""), 
            class_name=node.get("ClassName", ""),
            index=node.get("index"), 
            same_type_index=node.get("same_type_index"),
            name=node.get("Name", ""),
            process_name=p_name
        )
        segments.append(seg)

    if not segments:
        return ""
    return "//" + "/".join(segments)

def _make_segment(control_type, class_name=None, index=None, same_type_index=None, name=None, process_name=None):
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
            
    if process_name:
        attributes.append(f"@ProcessName='{process_name}'")

    if attributes:
        seg += f"[{' and '.join(attributes)}]"
        
    if position is not None:
        if OMIT_DEFAULT_INDEX and position == 1 and not attributes:
            pass 
        elif OMIT_DEFAULT_INDEX and position == 1 and attributes:
            pass 
        else:
            seg += f"[{position}]"
            
    return seg

def _short_type(control_type):
    if USE_SHORT_XPATH and control_type.endswith("Control"):
        return control_type[:-7]
    return control_type

def _escape_xpath_string(s):
    return s.replace("'", "&apos;")