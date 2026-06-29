import os


def kill_stray_ngrok():
    """Best-effort cleanup for ngrok agents left behind by a killed main.py."""
    import signal
    import subprocess as _sp

    try:
        out = _sp.run(["pgrep", "-f", "ngrok"], capture_output=True, text=True, timeout=5)
    except Exception:
        return
    my_pid = os.getpid()
    for line in out.stdout.split():
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid == my_pid:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def port_is_in_use(host: str, port: int) -> bool:
    import socket

    check_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((check_host, port)) == 0

