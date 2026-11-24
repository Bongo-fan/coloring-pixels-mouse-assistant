"""Coloring Pixels 填色辅助器。

答案来自游戏安装目录里的原图，不截图识数字，也不改存档。
鼠标只负责在已经打开的游戏画面里选色和点击。
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import threading
import time
from ctypes import wintypes
from pathlib import Path

from level_data import load_levels
from palette_setting import show as show_palette_setting




user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

ULONG_PTR = ctypes.c_size_t
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_ESCAPE = 0x1B
SW_RESTORE = 9


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def send_input(item: INPUT) -> None:
    sent = user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item))
    if sent != 1:
        raise OSError("SendInput 失败。如果游戏是用管理员身份打开的，辅助器也需要用管理员身份打开。")


def tap_key(vk: int) -> None:
    down = INPUT()
    down.type = INPUT_KEYBOARD
    down.union.ki.wVk = vk
    send_input(down)
    time.sleep(0.055)
    up = INPUT()
    up.type = INPUT_KEYBOARD
    up.union.ki.wVk = vk
    up.union.ki.dwFlags = KEYEVENTF_KEYUP
    send_input(up)


def mouse_button(down: bool) -> None:
    item = INPUT()
    item.type = INPUT_MOUSE
    item.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
    send_input(item)


def click_at(x: int, y: int) -> None:
    # Windows uses normalized coordinates relative to the virtual desktop.
    # Submit the move and press together so other motion cannot split them.
    left, top, width, height = (user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))
    if not (left <= x < left + width and top <= y < top + height):
        raise ValueError("目标位置超出桌面范围")
    items = (INPUT * 2)()
    items[0].union.mi.dx = ((x-left)*65536 + 32768)//width
    items[0].union.mi.dy = ((y-top)*65536 + 32768)//height
    items[0].union.mi.dwFlags = 0x8000 | 0x4000 | 0x0001
    items[1].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    try:
        if user32.SendInput(2, items, ctypes.sizeof(INPUT)) != 2:
            raise OSError("Windows 未接受鼠标输入")
        time.sleep(0.055)
    finally:
        mouse_button(False)


def escape_pressed() -> bool:
    return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def find_game_window() -> int | None:
    found: list[int] = []
    process_query = 0x1000

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        executable = ""
        process = kernel32.OpenProcess(process_query, False, pid.value)
        if process:
            name = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            if kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
                executable = name.value
            kernel32.CloseHandle(process)
        if executable.lower().endswith("\\coloringpixels.exe"):
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def focus_game() -> bool:
    hwnd = find_game_window()
    if not hwnd:
        return False
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    current_thread = kernel32.GetCurrentThreadId()
    attached = False
    if foreground_thread and foreground_thread != current_thread:
        attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if attached:
        user32.AttachThreadInput(current_thread, foreground_thread, False)
    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


def steam_libraries() -> list[Path]:
    import winreg

    roots = []
    for hive, key, value in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ):
        try:
            with winreg.OpenKey(hive, key) as entry:
                roots.append(Path(winreg.QueryValueEx(entry, value)[0]))
        except OSError:
            continue
    roots.extend(Path(os.environ.get(key, fallback)) / "Steam" for key, fallback in (
        ("ProgramFiles(x86)", r"C:\Program Files (x86)"), ("ProgramFiles", r"C:\Program Files")
    ))
    libraries = list(roots)
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            metadata = vdf.read_text(encoding="utf-8-sig", errors="replace")
            libraries.extend(Path(match.replace("\\\\", "\\")) for match in
                             re.findall(r'"path"\s+"([^"]+)"', metadata))
    return list(dict.fromkeys(libraries))


def find_resources() -> Path:
    relative = Path("ColoringPixels_Data/resources.assets")
    override = os.environ.get("COLORING_PIXELS_GAME_DIR")
    if override:
        resource = Path(override) / relative
        if resource.is_file():
            return resource
        raise FileNotFoundError(f"COLORING_PIXELS_GAME_DIR: {resource}")
    for library in steam_libraries():
        resource = library / "steamapps/common/Coloring Pixels" / relative
        if resource.is_file():
            return resource
    raise FileNotFoundError("找不到游戏。请设置 COLORING_PIXELS_GAME_DIR 为游戏安装目录。")



user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND


def cell_stream(level, grouped):
    cells = ((x, y, level.data[x * level.height + y])
             for y in range(level.height) for x in range(level.width))
    filled = (cell for cell in cells if cell[2] > 0)
    return sorted(filled, key=lambda cell: cell[2]) if grouped else filled


def validate_bounds(level, first, last):
    for span, count in zip((last[0]-first[0], last[1]-first[1]), (level.width, level.height)):
        if count > 1 and span < count-1:
            raise ValueError("两角距离太小或顺序相反，请重新记录网格中心。")
    if level.width > 1 and level.height > 1:
        dx = (last[0]-first[0])/(level.width-1)
        dy = (last[1]-first[1])/(level.height-1)
        if abs(dx-dy) > max(0.12*max(dx,dy), 0.6):
            raise ValueError("标出的格子不是正方形。请确认所选图片、缩放和两角位置。")


def point_for(level, first, last, x, y):
    return (round(first[0] + (last[0]-first[0])*x/max(1,level.width-1)),
            round(first[1] + (last[1]-first[1])*y/max(1,level.height-1)))


def check_window(hwnd, point):
    if (user32.GetForegroundWindow() != hwnd or
            user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(*point)), 2) != hwnd):
        raise RuntimeError("目标位置被遮挡或游戏已失去焦点，请重新标定。")


def paint(level, first, last, grouped, single, report, cancelled):
    validate_bounds(level, first, last)
    hwnd = find_game_window()
    if not hwnd or not focus_game():
        raise RuntimeError("请先打开 Coloring Pixels 并进入选定的图。")
    check_window(hwnd, first)
    check_window(hwnd, last)
    previous = None
    done = 0
    for x, y, color in cell_stream(level, grouped):
        if cancelled.is_set() or escape_pressed():
            return f"已停止，本次点击 {done} 格。"
        pt = point_for(level, first, last, x, y)
        check_window(hwnd, pt)
        if color != previous:
            for digit in f"{color:02d}":
                check_window(hwnd, pt)
                tap_key(ord(digit))
                time.sleep(0.06)
            previous = color
        if cancelled.is_set() or escape_pressed():
            return f"已停止，本次点击 {done} 格。"
        check_window(hwnd, pt)
        click_at(*pt)
        done += 1
        time.sleep(0.045)
        if single:
            return f"已试填第 {y+1} 行、第 {x+1} 列，颜色 {color}。"
        if done % 50 == 0:
            report(f"已点击 {done} 格，当前颜色 {color}")
    return f"已发送 {done} 格的点击，请以游戏内完成提示为准。"


def run_gui(levels):
    import tkinter as tk
    from tkinter import ttk
    from queue import SimpleQueue, Empty

    root = tk.Tk()
    root.title("Coloring Pixels 填色辅助器")
    panel = ttk.Frame(root, padding=14)
    panel.pack(fill="both", expand=True)
    labels = {v.label: v for v in levels}
    selected = tk.StringVar(value=levels[0].label)
    search = tk.StringVar()
    status = tk.StringVar(value="请选择游戏中打开的图片。")
    grouped = tk.BooleanVar(value=True)
    corners = [None, None]
    stop = threading.Event()
    updates = SimpleQueue()
    busy = False
    ttk.Label(panel, text="输入书名或图名筛选，再选择当前关卡").pack(anchor="w")
    entry = ttk.Entry(panel, textvariable=search)
    entry.pack(fill="x")
    picker = ttk.Combobox(panel, textvariable=selected, values=list(labels), state="readonly", width=60)
    picker.pack(fill="x", pady=4)

    def reset(*_):
        corners[:] = [None, None]
        level = labels.get(selected.get())
        status.set(f"{level.width} × {level.height}，{level.colors} 色。" if level else "没有匹配的关卡")

    def filter_levels(*_):
        hits = [key for key,v in labels.items() if search.get().casefold() in (key+' '+v.title).casefold()]
        picker.configure(values=hits)
        selected.set(hits[0] if hits else "")
        reset()

    search.trace_add("write", filter_levels)
    picker.bind("<<ComboboxSelected>>", reset)
    ttk.Label(panel,text="整张图保持可见，请依次记录左上格和右下格中心。").pack()
    ttk.Button(panel, text="游戏外切换已完成颜色显示", command=lambda:show_palette_setting(root)).pack()
    row = ttk.Frame(panel)
    row.pack()
    def record(index):
        if busy or not selected.get():
            return
        hwnd = find_game_window()
        if not hwnd or not focus_game():
            status.set("请先打开游戏并进入这张图。")
            return
        corners[index] = None
        def capture():
            p = wintypes.POINT()
            try:
                if not user32.GetCursorPos(ctypes.byref(p)):
                    raise RuntimeError("读取鼠标位置失败")
                check_window(hwnd, (p.x,p.y))
                corners[index] = (p.x,p.y)
                if all(corners):
                    validate_bounds(labels[selected.get()], *corners)
                status.set(f"左上 {corners[0]}    右下 {corners[1]}")
            except Exception as err:
                corners[index] = None
                status.set(str(err))
            root.lift()
            root.focus_force()
        root.after(3000, capture)

    for i, label in enumerate(("记录左上格", "记录右下格")):
        ttk.Button(row,text=label,command=lambda i=i:record(i)).pack(side="left", padx=3)
    for value, label in ((True,"逐颜色填充"),(False,"从左上到右下逐格填充")):
        ttk.Radiobutton(panel,text=label,variable=grouped,value=value).pack(anchor="w")
    def start(single):
        nonlocal busy
        if busy:
            return
        if not all(corners) or selected.get() not in labels:
            status.set("请选择当前图片，并记录两个格子的中心。")
            return
        level, first, last, mode = labels[selected.get()], *corners, grouped.get()
        stop.clear()
        busy = True
        def work():
            try:
                result = paint(level, first, last, mode, single, lambda s:updates.put((False,s)), stop)
            except Exception as err:
                result = str(err)
            updates.put((True,result))
        threading.Thread(target=work,daemon=True).start()

    actions = ttk.Frame(panel)
    actions.pack(pady=7)
    for label, fn in (("试填一格",lambda:start(True)),("开始整图",lambda:start(False)),("停止 (Esc)",stop.set)):
        ttk.Button(actions,text=label,command=fn).pack(side="left")
    ttk.Label(panel,textvariable=status,wraplength=515).pack(anchor="w")
    def poll():
        nonlocal busy
        try:
            while True:
                finished, message = updates.get_nowait()
                status.set(message)
                if finished:
                    busy = False
        except Empty:
            pass
        root.after(90,poll)
    poll()
    root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    enable_dpi_awareness()
    levels = load_levels(find_resources())
    if args.check:
        for level in levels:
            if min(level.data) < 0 or max(level.data) > level.colors:
                raise ValueError(level.label)
        print(f"Validated {len(levels)} levels.")
    else:
        run_gui(levels)
