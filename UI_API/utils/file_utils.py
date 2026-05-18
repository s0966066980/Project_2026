"""Shared file I/O helpers."""


def write_binary_file(path: str, data: bytes):
    with open(path, "wb") as f:
        f.write(data)
