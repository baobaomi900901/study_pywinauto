from pywinauto import Application
import time

# 打开软件
app = Application(backend='uia')
time.sleep(1) # 防止 程序未打开时连接失败

app.connect(handle=1118314)

print(app.windows())

np = app['软件机器人管理系统']
np.dump_tree()
