import json
import subprocess
from pathlib import Path

# 当前目录
ROOT = Path(__file__).resolve().parent

def get_version():
    """使用 uv 获取版本号"""
    result = subprocess.run(
        ["uv", "version", "--output-format", "json"],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    return data["package_name"], data["version"]

def generate_version_file(version: str) -> Path:
    """构建前生成 _version.py"""
    version_file = ROOT / "_version.py"
    version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    print(f"[build] 已生成 _version.py ({version})")
    return version_file

def build_exe(name, version: str):
    """调用 Nuitka 打包"""
    print(f"打包信息: name={name}, version={version}")

    cmd = [
        "uv", "run", "python", "-m",
        "nuitka",
        "--assume-yes-for-downloads",
        f"--product-name={name}",
        f"--file-version={version}",
        f"--product-version={version}",
        "main.py"
    ]

    subprocess.run(cmd, check=True)

    print("[build] Nuitka 打包完成")

def main():
    package_name, version = get_version()
    ver_file = generate_version_file(version)
    try:
        build_exe(package_name, version)
    finally:
        ver_file.unlink(missing_ok=True)
        print("[build] 已删除 _version.py")


if __name__ == "__main__":
    main()