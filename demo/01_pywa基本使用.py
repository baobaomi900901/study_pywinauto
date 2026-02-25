from pywinauto import Application
import time
# import sys
# import io

# sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 实例类, backend 默认值为 win32, 适用场景不一样
# app = Application(backend='win32')
app = Application(backend='uia')

# app.start('notepad') # 打开记事本

# 完整路径打开
# path = "C:\Program Files (x86)\Tabby\Tabby.exe"
# app.start(path)

time.sleep(1) # 防止 程序未打开时连接失败

# 连接程序，connect(), 参数如下:
# process：目标器的进程号
# handle：目标的窗口句柄
# path：用于启动目标器的路径
# timeout：进程启动的超时（如果指定了路径，则相关）

# app.connect(process=7488)
# app.connect(handle=133100)
# app.connect(path='Notepad.exe')
# app.connect(title='新建 文本文档.txt - Notepad')
app.connect(title_re='.*.txt', timeout='1000')  # 正则 match

# 打印窗体
# print(app.windows())

# 查看窗体有哪些功能
# 功能一样, 用第一个
# app['新建 文本文档.txt - Notepad'].dump_tree()
# app['新建 文本文档.txt - Notepad'].print_constrol_identifiers()

# 简写
np = app['pywinauto_示例.txt - Notepad']
# np.dump_tree()

# doc = np.child_window(title="pywinauto_示例.txt - Notepad", control_type="Window") 

# doc.type_keys("bbm900901")

# np.type_keys("bbm900901")
# np.type_keys("^a{DELETE}bbm900901") 

document = np.child_window(title="123", control_type="Document")
document.type_keys("bbm900901")