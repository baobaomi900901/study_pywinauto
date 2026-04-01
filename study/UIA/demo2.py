import uiautomation as auto
from lxml import etree

def control_to_lxml(control, parent=None):
    tag = control.ControlTypeName.replace(" ", "") or "UnknownControl"
    attrs = {
        "Name": control.Name or "",
        "AutomationId": control.AutomationId or "",
        "ClassName": control.ClassName or "",
        "IsEnabled": str(control.IsEnabled),
    }
    elem = etree.SubElement(parent, tag, attrs) if parent is not None \
           else etree.Element(tag, attrs)
    for child in control.GetChildren():
        control_to_lxml(child, elem)
    return elem

win = auto.WindowControl(Name="无标题.txt - Notepad")
root = control_to_lxml(win)

# 直接 XPath 查询，拿到 XML 节点
result_nodes = root.xpath('//TextControl[@Name="文件"]')

# 再根据节点的属性反查回真实控件（需要你自己维护映射）

print(result_nodes)
