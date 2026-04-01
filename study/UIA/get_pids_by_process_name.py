# 通过 进程名称 去找到 pid(可能多个)

import psutil
import os

def get_pids_by_name(process_name: str, case_sensitive: bool = True) -> list:
    """
    根据进程名获取所有匹配的进程 PID 列表。
    支持不带扩展名的名称（如 'uTools' 可匹配 'uTools.exe'）。

    :param process_name: 要查找的进程名，可带或不带扩展名（如 'notepad.exe' 或 'notepad'）
    :param case_sensitive: 是否区分大小写，默认为 True
    :return: 匹配的 PID 列表
    """
    pids = []
    # 如果传入的名称不包含 '.'，则视为基本名，匹配时去除进程名的扩展名
    match_basename = '.' not in process_name

    for proc in psutil.process_iter(['pid', 'name']):
        try:
            proc_name = proc.info['name']          # 进程名（含扩展名）
            if match_basename:
                # 提取进程名的基本名（不含扩展名）
                proc_base = os.path.splitext(proc_name)[0]
                name_to_compare = proc_base
                pattern = process_name
            else:
                name_to_compare = proc_name
                pattern = process_name

            if case_sensitive:
                if name_to_compare == pattern:
                    pids.append(proc.info['pid'])
            else:
                if name_to_compare.lower() == pattern.lower():
                    pids.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return pids

# 示例用法
if __name__ == '__main__':
    # 可以传入带扩展名或不带扩展名的名称
    process_name = "uTools"
    pids = get_pids_by_name(process_name, case_sensitive=False)
    print(f"找到的 PID: {pids}")



    