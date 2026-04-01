import paramiko

host = "192.168.104.153"
port = 22
user = "admin"
password = "1"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port, user, password)
sftp = client.open_sftp()

print("当前工作目录:", sftp.getcwd())

# 尝试列出 C:/
try:
    items = sftp.listdir("C:/")
    print("列出 C:/ 成功，前5项:", items[:5])
except Exception as e:
    print("列出 C:/ 失败:", e)

# 尝试创建目录
test_dir = "C:/test_sftp_temp"
try:
    sftp.mkdir(test_dir)
    print(f"创建 {test_dir} 成功")
    sftp.rmdir(test_dir)
    print("删除成功")
except Exception as e:
    print(f"创建 {test_dir} 失败:", e)

# 尝试相对路径
test_dir_rel = "test_sftp_temp"
try:
    sftp.mkdir(test_dir_rel)
    print(f"创建相对路径 {test_dir_rel} 成功")
    sftp.rmdir(test_dir_rel)
    print("删除成功")
except Exception as e:
    print(f"创建相对路径 {test_dir_rel} 失败:", e)

sftp.close()
client.close()