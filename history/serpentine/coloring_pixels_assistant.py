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
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from progress import read_progress, verify_completion
from viewport import View, client_rect, right_drag
from level_data import load_levels, default_camera_size
from palette_setting import show as show_palette_setting




user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
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


def click_at(x: int, y: int, hold=0.055, continuation=None) -> None:
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
        time.sleep(hold)
        if continuation:
            continuation()
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


def cell_stream(level, grouped, progress=None, tile=None):
    def pending():
        for y in range(level.height):
            columns = range(level.width) if y % 2 == 0 else range(level.width - 1, -1, -1)
            for x in columns:
                index = x * level.height + y
                color = level.data[index]
                if color > 0 and (progress is None or progress[index] != color):
                    yield x, y, color

    def tile_key(cell):
        x, y, color = cell
        band, column = y // tile[1], x // tile[0]
        return band, column if band % 2 == 0 else -column, color

    if grouped:
        return sorted(pending(), key=tile_key if tile else lambda cell: cell[2])
    return pending()


def check_window(hwnd, point):
    if (user32.GetForegroundWindow() != hwnd or
            user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(*point)), 2) != hwnd):
        raise RuntimeError("目标位置被遮挡或游戏已失去焦点，请切回游戏，重新进图后重置视角。")


def paint(level, view, grouped, single, report, cancelled, progress=None, fast=False):
    hwnd = find_game_window()
    if not hwnd or not focus_game():
        raise RuntimeError("请先打开 Coloring Pixels 并进入选定的图。")
    if client_rect(user32, hwnd) != view.rect:
        raise RuntimeError("窗口已移动或改变大小，请重新进入关卡并重置视角。")
    def pan(center, delta):
        if client_rect(user32, hwnd) != view.rect:
            raise RuntimeError("游戏窗口已改变，请重新进入关卡并重置视角。")
        right_drag(user32, hwnd, center, delta, check_window, lambda: cancelled.is_set() or escape_pressed())
    previous = None
    done = 0
    cells = iter(cell_stream(level, grouped, progress, view.tile))
    cell = next(cells, None)
    while cell is not None:
        x, y, color = cell
        if cancelled.is_set() or escape_pressed():
            cancelled.set()
            return f"已停止，本次处理 {done} 格。"
        pt = view.locate(x, y, pan)
        if client_rect(user32, hwnd) != view.rect:
            raise RuntimeError("游戏窗口已改变，请重新进入关卡并重置视角。")
        check_window(hwnd, pt)
        if color != previous:
            for digit in f"{color:02d}":
                check_window(hwnd, pt)
                tap_key(ord(digit))
                time.sleep(0.06)
            previous = color
        if cancelled.is_set() or escape_pressed():
            cancelled.set()
            return f"已停止，本次处理 {done} 格。"
        check_window(hwnd, pt)
        cell = next(cells, None)
        def continue_row():
            nonlocal cell, done
            last_x = x
            direction = 1 if y % 2 == 0 else -1
            while cell == (last_x + direction, y, color):
                if cancelled.is_set() or escape_pressed():
                    cancelled.set()
                    break
                nx = cell[0]
                target = view.point(nx, y)
                if any(abs(v-c)>r for v,c,r in zip(target,view.center,view.reach)):
                    break
                check_window(hwnd,target)
                if not user32.SetCursorPos(*target):
                    raise RuntimeError("无法移动鼠标")
                time.sleep(0.028)
                done += 1
                last_x = nx
                cell = next(cells,None)
        click_at(*pt, hold=0.027 if fast else 0.055,
                 continuation=continue_row if fast and not single else None)
        done += 1
        time.sleep(0.023 if fast else 0.045)
        if single:
            return f"已试填第 {y+1} 行、第 {x+1} 列，颜色 {color}。"
        if done % 50 == 0:
            report(f"已点击 {done} 格，当前颜色 {color}")
    return f"已处理 {done} 格。"


def run_gui(levels, camera_size):
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
    fast = tk.BooleanVar(value=True)
    power_off = tk.BooleanVar(value=False)
    shutdown_job = None
    views = {}
    stop = threading.Event()
    updates = SimpleQueue()
    busy = False
    ttk.Label(panel, text="输入书名或图名筛选，再选择当前关卡").pack(anchor="w")
    entry = ttk.Entry(panel, textvariable=search)
    entry.pack(fill="x")
    picker = ttk.Combobox(panel, textvariable=selected, values=list(labels), state="readonly", width=60)
    picker.pack(fill="x", pady=4)

    def reset(*_):
        views.clear()
        level = labels.get(selected.get())
        status.set(f"{level.width} × {level.height}，{level.colors} 色。" if level else "没有匹配的关卡")

    def filter_levels(*_):
        hits = [key for key,v in labels.items() if search.get().casefold() in (key+' '+v.title).casefold()]
        picker.configure(values=hits)
        selected.set(hits[0] if hits else "")
        reset()

    search.trace_add("write", filter_levels)
    picker.bind("<<ComboboxSelected>>", reset)
    ttk.Label(panel, wraplength=515, text="自动模式：重新进入所选关卡并保持默认缩放。程序会自行平移画布。停止后保持视角即可继续；手动平移、缩放或重新进图后，请重新进图并点“重置视角”。").pack(pady=6)
    ttk.Checkbutton(panel,text="快速点击（低帧率时可关闭）",variable=fast).pack(anchor="w")
    ttk.Button(panel,text="已重新进图 · 重置视角",command=reset).pack()
    ttk.Button(panel, text="游戏外切换已完成颜色显示", command=lambda:show_palette_setting(root)).pack()
    ttk.Checkbutton(panel, text="整图保存并复查通过后关机（60 秒内可取消）",
                    variable=power_off).pack(anchor="w")
    for value, label in ((True,"逐颜色填充"),(False,"从左上开始蛇形逐格填充")):
        ttk.Radiobutton(panel,text=label,variable=grouped,value=value).pack(anchor="w")
    def start(single):
        nonlocal busy
        if busy or shutdown_job is not None:
            return
        level = labels.get(selected.get())
        if level is None:
            status.set("请选择游戏中打开的图片。")
            return
        hwnd = find_game_window()
        if not hwnd:
            status.set("请打开游戏并进入所选关卡。")
            return
        if level.label not in views:
            views[level.label] = View(client_rect(user32, hwnd), level, camera_size)
        view = views[level.label]
        mode, rapid, shutdown = grouped.get(), fast.get(), power_off.get()
        stop.clear()
        busy = True
        def work():
            try:
                progress = read_progress(level)
                remaining = sum(1 for _ in cell_stream(level, False, progress))
                if not remaining:
                    updates.put(("done", "已保存进度显示此图已完成。"))
                    return
                updates.put(("progress", f"按已保存的进度，还需填 {remaining} 格。"))
                result = paint(level, view, mode, single,
                               lambda text: updates.put(("progress", text)), stop, progress, rapid)
                if not single and not stop.is_set() and not escape_pressed():
                    updates.put(("progress", "等待游戏自动保存，再逐格复查。请保持关卡打开。"))
                    left = verify_completion(level, stop, escape_pressed)
                    if not stop.is_set() and left == 0:
                        updates.put(("shutdown" if shutdown else "done", "已复查整张图，存档确认所有格子正确。"))
                        return
                    if not stop.is_set():
                        result += (f" 最新可读进度仍有 {left} 格未确认；可再次开始补填。"
                                   if left is not None else " 未读到有效进度，无法确认整图完成。")
                    else:
                        result += " 已取消复查。"
            except Exception as err:
                result = str(err)
            updates.put(("done", result))
        threading.Thread(target=work,daemon=True).start()

    def cancel():
        nonlocal shutdown_job
        stop.set()
        if shutdown_job is not None:
            root.after_cancel(shutdown_job)
            shutdown_job = None
            status.set("已取消关机。")

    def shutdown_after(seconds):
        nonlocal shutdown_job
        if seconds:
            status.set(f"复查完成。将在 {seconds} 秒后关机，点「停止 / 取消关机」可取消。")
            shutdown_job = root.after(1000, shutdown_after, seconds - 1)
            return
        shutdown_job = None
        try:
            subprocess.run(["shutdown.exe", "/s", "/t", "0"], check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as err:
            status.set(f"关机失败：{err}")

    actions = ttk.Frame(panel)
    actions.pack(pady=7)
    for label, fn in (("试填一格",lambda:start(True)),("开始整图",lambda:start(False)),("停止 / 取消关机",cancel)):
        ttk.Button(actions,text=label,command=fn).pack(side="left")
    ttk.Label(panel,textvariable=status,wraplength=515).pack(anchor="w")
    def poll():
        nonlocal busy
        try:
            while True:
                kind, message = updates.get_nowait()
                status.set(message)
                if kind != "progress":
                    busy = False
                if kind == "shutdown" and not stop.is_set():
                    shutdown_after(60)
        except Empty:
            pass
        root.after(90,poll)
    root.bind("<Escape>", lambda _event: cancel())
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
        run_gui(levels, default_camera_size(find_resources()))
