"""Control the RemoveDone preference written by CrossLevelStorage.SaveMainMenuInfo."""
import codecs
import os
from pathlib import Path
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk

MAIN = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/ToastieLabs/ColoringPixels/Main.save"
FLAG = b"RemoveDone"


def parts(data):
    body = data.removeprefix(codecs.BOM_UTF8)
    body.decode("utf-8")
    if not body or b"\0" in body or not body.endswith(b":"):
        raise ValueError("配置格式与已验证的游戏版本不同。")
    return body[:-1].split(b":")


def update(path, hide):
    listing = subprocess.run(
        ["tasklist.exe", "/fi", "imagename eq ColoringPixels.exe", "/fo", "csv", "/nh"],
        capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    if b'"coloringpixels.exe"' in listing.stdout.lower():
        raise RuntimeError("请正常退出游戏，再切换设置。")
    original = path.read_bytes()
    fields = parts(original)
    if (FLAG in fields) == hide:
        return
    if hide:
        fields.append(FLAG)
    else:
        fields = [field for field in fields if field != FLAG]
    new = (codecs.BOM_UTF8 if original.startswith(codecs.BOM_UTF8) else b"") + b":".join(fields) + b":"
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            stream.write(new)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != original:
            raise RuntimeError("游戏配置刚被其他程序更新，请重试。")
        os.replace(temp, path)
    finally:
        if temp:
            temp.unlink(missing_ok=True)


def show(parent=None):
    window = tk.Toplevel(parent) if parent else tk.Tk()
    window.title("Coloring Pixels · 已完成颜色")
    box = ttk.Frame(window, padding=16)
    box.pack()
    status = tk.StringVar(master=window)
    def refresh():
        try:
            hidden = FLAG in parts(MAIN.read_bytes())
            status.set("当前设置：" + ("隐藏已完成颜色" if hidden else "显示已完成颜色"))
        except (OSError, ValueError) as exc:
            status.set(str(exc))
    def apply(hidden):
        try:
            update(MAIN, hidden)
            refresh()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            status.set(str(exc))
    ttk.Label(box, text="正常退出游戏后切换，下次启动游戏生效。").pack()
    ttk.Label(box, textvariable=status, wraplength=460).pack(pady=8)
    ttk.Button(box, text="测试用 · 显示已完成颜色", command=lambda: apply(False)).pack(fill="x")
    ttk.Button(box, text="日常游玩 · 隐藏已完成颜色", command=lambda: apply(True)).pack(fill="x")
    refresh()
    if not parent:
        window.mainloop()


if __name__ == "__main__":
    show()
