from pywinauto.application import Application

app = Application(backend='uia').connect(title_re="新建 文本文档.txt")
print(app.windows())