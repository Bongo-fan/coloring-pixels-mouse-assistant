"""Read progress in the same column order as the game's LoadSave."""
from array import array
from pathlib import Path
import os


def read_progress(level, root=None):
    if root is None:
        root = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/ToastieLabs/ColoringPixels"
    folder = root / level.book
    base = folder / level.name
    if Path(str(base) + ".toast").is_file():
        raise ValueError("此关为 New Game+ 特殊进度，当前版本无法核对。")
    for suffix in (".save", "_backup.save"):
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
