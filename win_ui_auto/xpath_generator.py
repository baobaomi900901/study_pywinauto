# win_ui_auto/xpath_generator.py
USE_SHORT_XPATH = True
OMIT_DEFAULT_INDEX = True


def generate_xpath(control_info, parent_chain):
    """
    生成简洁的 XPath，自动使用 // 跳过中间层
    格式：//Window[@ClassName='Notepad']//TargetType[@Name='...']
    """
    # 过滤桌面
    filtered_parents = [p for p in parent_chain if not p.get("is_desktop", False)]
    all_nodes = filtered_parents + [control_info]

    # 1. 寻找应用外壳（Window 或带有 is_app 标记的节点）
    shell_index = 0
    for i, node in enumerate(all_nodes):
        if node.get("is_app") or node.get("ControlType") == "WindowControl":
            shell_index = i
            break

    # 2. 获取外壳节点信息
    shell_node = all_nodes[shell_index]
    shell_type = _short_type(shell_node.get("ControlType", ""))
    shell_attrs = []
    if shell_node.get("ClassName"):
        shell_attrs.append(f"@ClassName='{_escape_xpath_string(shell_node['ClassName'])}'")
    if shell_node.get("Name"):
        shell_attrs.append(f"@Name='{_escape_xpath_string(shell_node['Name'])}'")

    # 进程名可作为额外锁定条件（可选）
    app_name = control_info.get("application", {}).get("name", "")
    if app_name:
        shell_attrs.append(f"@ProcessName='{app_name}'")

    shell_seg = f"{shell_type}[{' and '.join(shell_attrs)}]"

    # 3. 目标控件片段
    target_type = _short_type(control_info.get("ControlType", ""))
    target_attrs = []
    if control_info.get("Name"):
        target_attrs.append(f"@Name='{_escape_xpath_string(control_info['Name'])}'")
    elif control_info.get("ClassName"):
        target_attrs.append(f"@ClassName='{_escape_xpath_string(control_info['ClassName'])}'")
    
    target_seg = target_type
    if target_attrs:
        target_seg += f"[{' and '.join(target_attrs)}]"
    else:
        # 没有任何标识属性时，必须加索引
        pos = control_info.get("same_type_index", 0) + 1
        target_seg += f"[{pos}]"

    # 4. 组合：用 // 连接外壳和目标
    if shell_seg and target_seg:
        return f"//{shell_seg}//{target_seg}"
    else:
        # 保底：传统逐层生成
        return _generate_fallback(control_info, parent_chain)


def _generate_fallback(control_info, parent_chain):
    """传统逐层生成（保留作为备用）"""
    filtered_parents = [p for p in parent_chain if not p.get("is_desktop", False)]
    all_nodes = filtered_parents + [control_info]
    segments = []
    app_name = control_info.get("application", {}).get("name", "")
    for i, node in enumerate(all_nodes):
        seg = _make_segment(
            control_type=node.get("ControlType", ""),
            class_name=node.get("ClassName", ""),
            same_type_index=node.get("same_type_index"),
            name=node.get("Name", ""),
            process_name=app_name if i == 0 else None
        )
        segments.append(seg)
    return "//" + "/".join(segments)


def _make_segment(control_type, class_name=None, same_type_index=None, name=None, process_name=None):
    seg = _short_type(control_type)
    attributes = []
    position = same_type_index + 1 if same_type_index is not None else None

    if name and name.strip():
        attributes.append(f"@Name='{_escape_xpath_string(name)}'")
    elif class_name and class_name.strip():
        attributes.append(f"@ClassName='{_escape_xpath_string(class_name)}'")
    if process_name:
        attributes.append(f"@ProcessName='{process_name}'")

    if attributes:
        seg += f"[{' and '.join(attributes)}]"

    has_no_identity = not (name or class_name or process_name)
    is_first_and_omit = (OMIT_DEFAULT_INDEX and position == 1)

    if has_no_identity:
        if position is not None:
            seg += f"[{position}]"
    else:
        if position is not None and not is_first_and_omit:
            seg += f"[{position}]"
    return seg


def _short_type(control_type):
    if USE_SHORT_XPATH and control_type.endswith("Control"):
        return control_type[:-7]
    return control_type


def _escape_xpath_string(s):
    return s.replace("'", "&apos;")