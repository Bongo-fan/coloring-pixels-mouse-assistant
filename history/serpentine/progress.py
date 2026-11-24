"""Read progress in the same column order as the game's LoadSave."""
from array import array
from pathlib import Path
import os


def read_progress(level, root=None, *, allow_backup=True):
    if root is None:
        root = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/ToastieLabs/ColoringPixels"
    folder = root / level.book
    base = folder / level.name
    if Path(str(base) + ".toast").is_file():
        raise ValueError("此关为 New Game+ 特殊进度，当前版本无法核对。")
    suffixes = (".save", "_backup.save") if allow_backup else (".save",)
    for suffix in suffixes:
        path = Path(str(base) + suffix)
        try:
            raw = path.read_text(encoding="utf-8-sig").strip().rstrip(":")
        except FileNotFoundError:
            continue
        values = array("h", map(int, raw.split(":")))
        if len(values) != len(level.data):
            raise ValueError("进度格数和关卡不一致，请等游戏保存后重试。")
        return values
    return None


def verify_completion(level, stop, escape_pressed, timeout=50):
    """Wait for autosave and compare every playable cell to the level metadata."""
    import time

    deadline = time.monotonic() + timeout
    remaining = None
    while not stop.is_set():
        if escape_pressed():
            stop.set()
            break
        try:
            progress = read_progress(level, allow_backup=False)
            if progress is not None:
                remaining = sum(color > 0 and progress[i] != color
                                for i, color in enumerate(level.data))
                if remaining == 0:
                    return 0
        except (OSError, ValueError):
            pass  # The game may be replacing the file during autosave.
        if time.monotonic() >= deadline:
            break
        stop.wait(0.5)
    return remaining
