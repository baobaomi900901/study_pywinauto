import psutil

for proc in psutil.process_iter([
    'pid',               # 进程ID
    'name',              # 进程名称
    'ppid',              # 父进程ID
    'status',            # 进程状态（如 running, sleeping 等）
    'create_time',       # 进程创建时间（Unix 时间戳）
    'exe',               # 可执行文件路径
    'cwd',               # 当前工作目录
    'cmdline',           # 命令行参数列表
    'memory_info',       # 内存信息（如 RSS, VMS 等）
    'memory_percent',    # 内存使用百分比
    'cpu_times',         # CPU 时间（用户态、系统态等）
    'cpu_percent',       # CPU 使用百分比
    'io_counters',       # I/O 计数器（读写字节数等）
    'num_threads',       # 线程数量
    'num_handles',       # 句柄数量（仅 Windows）
    'username',          # 运行进程的用户名
    'threads',           # 线程信息列表
    'open_files',        # 打开的文件列表（可能因权限受限）
    'environ'            # 环境变量字典
]):
  
  print(f"进程名: {proc.info['name']}, 工作目录: {proc.info['cwd']}")