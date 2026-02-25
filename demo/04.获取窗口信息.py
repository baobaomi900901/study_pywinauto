from pywinauto.application import Application

app = Application(backend='uia').connect(title_re="Tabby")
print(app.windows())

dlg = app.window(title_re="Tabby")
# 获取对话框
dlg.print_control_identifiers()