"""一键启动 MCP + Web 服务（开发环境）"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
PORTS = {"MCP": 7001, "Web": 7003}


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(port: int) -> bool:
    """释放占用端口的进程（Windows）"""
    if not port_in_use(port):
        return True
    if sys.platform != "win32":
        print(f"[WARN] 端口 {port} 已被占用，请手动结束占用进程后重试")
        return False
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{port}"',
            shell=True,
            text=True,
            errors="ignore",
        )
        pids = set()
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            if pid.isdigit() and int(pid) > 0:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                    check=False,
                )
        time.sleep(1)
        return not port_in_use(port)
    except Exception as e:
        print(f"[WARN] 无法释放端口 {port}: {e}")
        return False


def wait_port(port: int, timeout: float = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_in_use(port):
            return True
        time.sleep(0.3)
    return False


def main():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    print("正在检查端口...")
    for name, port in PORTS.items():
        if port_in_use(port):
            print(f"  端口 {port} ({name}) 已被占用，尝试释放...")
            if not free_port(port):
                print(f"[错误] 无法释放端口 {port}，请先关闭占用该端口的程序后重试。")
                print("  可执行: netstat -ano | findstr \":7001\"  查看 PID")
                sys.exit(1)
            print(f"  端口 {port} 已释放")

    procs = []
    commands = [
        ([sys.executable, "mcp_server.py"], "MCP", 7001),
        ([sys.executable, "web_app.py"], "Web", 7003),
    ]

    print("\n正在启动 AutoCityIntro 服务...")
    for cmd, name, port in commands:
        p = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        if not wait_port(port, timeout=20):
            p.terminate()
            print(f"[错误] {name} (:{port}) 启动超时，请单独运行查看报错:")
            print(f"  python {cmd[1]}")
            sys.exit(1)
        procs.append((p, name, port))
        print(f"  [OK] {name} :{port} (pid={p.pid})")

    print("\n访问 Web 界面: http://localhost:7003")
    print("按 Ctrl+C 停止全部服务\n")

    try:
        while True:
            for p, name, port in procs:
                if p.poll() is not None:
                    print(f"\n[错误] {name} (:{port}) 意外退出，code={p.returncode}")
                    print("请单独运行对应脚本查看详细错误:")
                    print(f"  python {'mcp_server.py' if port == 7001 else 'web_app.py'}")
                    for p2, n2, _ in procs:
                        if p2.poll() is None:
                            p2.terminate()
                    sys.exit(1)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        for p, name, _ in procs:
            if p.poll() is None:
                p.terminate()
                print(f"  已停止 {name}")


if __name__ == "__main__":
    main()
