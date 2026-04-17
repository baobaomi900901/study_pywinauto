# win_ui_auto/xpath_generator.py
USE_SHORT_XPATH = True
OMIT_DEFAULT_INDEX = True


def generate_xpath(control_info, parent_chain):
    """
    稳妥版 XPath 生成器：兼顾“抗 UI 结构变化”与“精准定位”
    """
    filtered_parents = [p for p in parent_chain if not p.get("is_desktop", False)]
    all_nodes = filtered_parents + [control_info]

    # ==========================================
    # 1. 稳妥的外壳寻找 (保留对 CEF 等特殊框架的兼容)
    # ==========================================
    shell_index = 0
    # 倒序寻找，更贴近实际的应用容器
    for i in range(len(all_nodes) - 1, -1, -1):
        node = all_nodes[i]
        is_app_flag = node.get("is_app", False)
        is_window = node.get("ControlType") == "WindowControl"
        is_cef = "Chrome_WidgetWin_1" in node.get("ClassName", "")

        if is_app_flag or is_window or is_cef:
            shell_index = i
            break

    # ==========================================
    # 2. 获取外壳与进程特征
    # ==========================================
    shell_node = all_nodes[shell_index]
    shell_type = _short_type(shell_node.get("ControlType", ""))
    shell_attrs = []
    if shell_node.get("AutomationId"):
        shell_attrs.append(f"@AutomationId='{_escape_xpath_string(shell_node['AutomationId'])}'")
    if shell_node.get("ClassName"):
        shell_attrs.append(f"@ClassName='{_escape_xpath_string(shell_node['ClassName'])}'")
    if shell_node.get("Name"):
        shell_attrs.append(f"@Name='{_escape_xpath_string(shell_node['Name'])}'")

    app_name = control_info.get("application", {}).get("name", "")
    if app_name:
        shell_attrs.append(f"@ProcessName='{app_name}'")

    shell_seg = f"{shell_type}[{' and '.join(shell_attrs)}]" if shell_attrs else shell_type

    # ==========================================
    # 3. 动态降级策略：评估目标控件的“抗干扰能力”
    # ==========================================
    target_name = (control_info.get("Name") or "").strip()
    target_aid = (control_info.get("AutomationId") or "").strip()

    # 策略 A0：目标有稳定 AutomationId，优先用它跨级跳跃（通常比 Name 稳定）
    if target_aid:
        target_type = _short_type(control_info.get("ControlType", ""))
        target_seg = f"{target_type}[@AutomationId='{_escape_xpath_string(target_aid)}']"
        return f"//{shell_seg}//{target_seg}"

    # 策略 A：目标有明确 Name，允许使用 // 跨级跳跃 (抗 UI 结构变化)
    if target_name:
        target_type = _short_type(control_info.get("ControlType", ""))
        target_seg = f"{target_type}[@Name='{_escape_xpath_string(target_name)}']"

        # 如果同时有 ClassName，加上以增加双保险
        target_class = (control_info.get("ClassName") or "").strip()
        if target_class:
            target_seg = (
                f"{target_type}[@Name='{_escape_xpath_string(target_name)}' and "
                f"@ClassName='{_escape_xpath_string(target_class)}']"
            )

        return f"//{shell_seg}//{target_seg}"

    # 策略 B：目标特征极弱，强制回退逐层路径 (保精准)
    return _generate_fallback(control_info, parent_chain, shell_index)


def _generate_fallback(control_info, parent_chain, start_index=0):
    """
    稳妥逐层生成：从确定的外壳层开始，一步步向下精确定位
    """
    filtered_parents = [p for p in parent_chain if not p.get("is_desktop", False)]
    all_nodes = filtered_parents + [control_info]
    segments = []
    app_name = control_info.get("application", {}).get("name", "")

    for i in range(start_index, len(all_nodes)):
        node = all_nodes[i]
        seg = _make_segment(
            control_type=node.get("ControlType", ""),
            class_name=node.get("ClassName", ""),
            same_type_index=node.get("same_type_index"),
            name=node.get("Name", ""),
            automation_id=node.get("AutomationId", ""),
            process_name=app_name if i == start_index else None
        )
        segments.append(seg)
    # 关键：外壳到第一层用 '//'（允许跨过中间 Pane/Group），后续保持逐层 '/'
    # 这样既避免 Window->Document 必须“直接子节点”的脆弱约束，又不至于全程跨级导致误命中
    if len(segments) >= 2:
        return f"//{segments[0]}//" + "/".join(segments[1:])
    return "//" + "/".join(segments)


def _make_segment(control_type, class_name=None, same_type_index=None, name=None, automation_id=None, process_name=None):
    seg = _short_type(control_type)
    attributes = []
    position = same_type_index + 1 if same_type_index is not None else None

    if automation_id and str(automation_id).strip():
        attributes.append(f"@AutomationId='{_escape_xpath_string(str(automation_id))}'")
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