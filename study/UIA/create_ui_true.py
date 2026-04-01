import uiautomation as auto
import xml.etree.ElementTree as ET
from lxml import etree

def control_to_xml(control, parent=None):
    tag = control.ControlTypeName.replace(" ", "")  # e.g. "ButtonControl"
    attrs = {
        "Name":        control.Name or "",
        "AutomationId": control.AutomationId or "",
        "ClassName":   control.ClassName or "",
        "ControlType": control.ControlTypeName or "",
        "IsEnabled":   str(control.IsEnabled),
        "IsOffscreen": str(control.IsOffscreen),
    }
    elem = ET.SubElement(parent, tag, attrs) if parent is not None else ET.Element(tag, attrs)
    
    for child in control.GetChildren():
        control_to_xml(child, elem)
    
    return elem

# 抓取目标窗口
win = auto.WindowControl(Name="应用 – lite_oss – WinSCP")
root_elem = control_to_xml(win)

tree = ET.ElementTree(root_elem)
ET.indent(tree)  # Python 3.9+
tree.write("ui_tree.xml", encoding="utf-8", xml_declaration=True)