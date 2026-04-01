import paramiko
import os
import sys

def sftp_download(hostname, port, username, password, remote_path, local_path, key_filename=None):
    """
    通过 SFTP 从服务器下载文件到本地
    :param hostname: 服务器地址
    :param port: SSH 端口（默认22）
    :param username: 用户名
    :param password: 密码（若使用密钥可设为None）
    :param remote_path: 远程文件路径
    :param local_path: 本地保存路径（包含文件名）
    :param key_filename: 私钥文件路径（可选）
    """
    # 创建 SSH 客户端
    ssh = paramiko.SSHClient()
    # 自动添加主机密钥（生产环境建议严格校验）
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # 连接服务器
        print(f"正在连接 {hostname}:{port}...")
        ssh.connect(hostname, port=port, username=username,
                    password=password, key_filename=key_filename)
        print("连接成功")

        # 打开 SFTP 会话
        sftp = ssh.open_sftp()
        print("SFTP 会话已打开")

        # 检查远程文件是否存在
        try:
            sftp.stat(remote_path)
        except FileNotFoundError:
            print(f"错误: 远程文件 {remote_path} 不存在")
            sys.exit(1)

        # 确保本地目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir)
            print(f"创建本地目录: {local_dir}")

        # 下载文件
        print(f"正在下载 {remote_path} -> {local_path}")
        sftp.get(remote_path, local_path)
        print("下载成功")

        # 关闭 SFTP 会话
        sftp.close()
    except Exception as e:
        print(f"发生错误: {e}")
        sys.exit(1)
    finally:
        # 关闭 SSH 连接
        ssh.close()
        print("连接已关闭")

if __name__ == "__main__":
    # 配置参数（请根据实际情况修改）
    HOST = "192.168.104.153"        # Windows 服务器 IP
    PORT = 22                       # SSH 端口（默认22）
    USER = "admin"                  # 用户名
    PASS = "1"                      # 密码（若用密钥则设为 None）
    KEY_FILE = None                 # 私钥路径，如 "C:/path/to/private_key.ppk" 或 "id_rsa"
    REMOTE_FILE = "C:/Users/admin/moby/demo2.json"  # 远程文件路径
    LOCAL_FILE = "C:/Users/mobytang/Desktop/downloaded_demo2.json"  # 本地保存路径

    sftp_download(HOST, PORT, USER, PASS, REMOTE_FILE, LOCAL_FILE, KEY_FILE)