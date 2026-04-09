import re
import json
import subprocess
from pathlib import Path

# 当前目录
ROOT = Path(__file__).resolve().parent

def build_exe(name, version: str):
    """调用 Nuitka 打包"""
    print(f"打包信息: name={name}, version={version}")

    cmd = [
        "python", "-m",
        "nuitka",
        # "--mingw64",
        f"--product-name={name}",
        f"--file-version={version}",
        f"--product-version={version}",
        "find_text.py"
    ]

    subprocess.run(cmd, check=True)

    print(f"🎉 Nuitka 打包完成")

def main():
    build_exe('bbm', '1.0.0.0')


if __name__ == "__main__":
    main()