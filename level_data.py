"""Read the same fullLevelData arrays that CrossLevelStorage.LoadFile uses."""

from dataclasses import dataclass
import struct

import UnityPy


@dataclass
class Level:
    book: str
    name: str
    title: str
    width: int
    height: int
    colors: int
    data: memoryview

    @property
    def label(self):
        return f"{self.book} / {self.name}"


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 28  # MonoBehaviour header through m_Script

    def number(self):
        value, = struct.unpack_from("<i", self.data, self.pos)
        self.pos += 4
        return value

    def string(self):
        size = self.number()
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError("invalid Unity string")
        start = self.pos
        self.pos = (start + size + 3) & ~3
        return self.data[start:start + size].decode("utf-8")


def read_book(raw):
    r = Reader(raw)
    r.string()
    r.number()
    book = r.string()
    r.pos += 8
    r.string()
    r.number()
    r.string()
    r.string()
    count = r.number()
    if not 0 <= count <= 10000:
        raise ValueError("invalid level count")
    for _ in range(count):
        title = r.string()
        r.string()  # author
        name = r.string()
        r.pos += 12  # texture reference
        length = r.number()
        if length < 3 or r.pos + length * 2 > len(raw):
            raise ValueError(f"invalid level data: {book}/{name}")
        values = memoryview(raw)[r.pos:r.pos + length * 2].cast("h")
        w, h = values[:2]
        cells = w * h
        if w <= 0 or h <= 0 or cells + 2 >= length:
            raise ValueError(f"invalid grid: {book}/{name}")
        colors = values[cells + 2]
        if length != 3 + cells + 3 * colors:
            raise ValueError(f"invalid palette: {book}/{name}")
        yield Level(book, name, title, w, h, colors, values[2:cells + 2])
        r.pos = (r.pos + length * 2 + 3) & ~3
        r.string()
        r.string()
        r.number()


def load_levels(path):
    env = UnityPy.load(str(path))
    books = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        raw = obj.get_raw_data()
        if len(raw) >= 40 and raw[32:35].isdigit() and raw[35:36] == b"_":
            books.extend(read_book(raw))
    if not books:
        raise ValueError("资源中没有可读取的关卡")
    return books


def default_camera_size(resources):
    scene = UnityPy.load(str(resources.parent / "level1"))
    for obj in scene.objects:
        if obj.type.name == "Camera":
            camera = obj.read()
            if camera.orthographic and camera.m_GameObject.read().m_Name == "Main Camera":
                return camera.orthographic_size
    raise ValueError("无法读取游戏默认相机")
