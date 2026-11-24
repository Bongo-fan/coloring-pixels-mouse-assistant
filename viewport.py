"""Map cells to the freshly opened Unity orthographic view, then track right drags."""
import ctypes
from ctypes import wintypes
import time


def client_rect(api, hwnd):
    r = wintypes.RECT()
    corner = wintypes.POINT()
    if not api.GetClientRect(hwnd, ctypes.byref(r)) or not api.ClientToScreen(hwnd, ctypes.byref(corner)):
        raise RuntimeError("读取游戏窗口失败")
    return corner.x, corner.y, r.right, r.bottom


class View:
    def __init__(self, rect, level, camera_size):
        self.rect = rect
        left, top, w, h = rect
        self.center = (left + w//2, top + h//2)
        self.step = h / (2 * camera_size)
        self.origin = [left + w/2 + (0.5-level.width/2)*self.step,
                       top + h/2 + (0.5-level.height/2)*self.step]
        self.reach = (int(w*0.32), int(h*0.24))
        self.tile = tuple(max(1,int(r/self.step)) for r in self.reach)

    def point(self, x, y):
        return round(self.origin[0]+x*self.step), round(self.origin[1]+y*self.step)

    def locate(self, x, y, pan):
        while True:
            point = self.point(x,y)
            delta = tuple(c-p for c,p in zip(self.center,point))
            if all(abs(d)<=r for d,r in zip(delta,self.reach)):
                return point
            move = tuple(min(r,max(-r,d)) for r,d in zip(self.reach,delta))
            pan(self.center,move)
            for i in (0,1):
                self.origin[i] += move[i]


def right_drag(api, hwnd, center, delta, check, stopped):
    end = tuple(c+d for c,d in zip(center,delta))
    for pt in (center,end):
        check(hwnd,pt)
    if stopped():
        raise InterruptedError("已停止")
    api.SetCursorPos(*center)
    time.sleep(0.08)
    api.mouse_event(0x0008,0,0,0,0)
    try:
        time.sleep(0.065)
        check(hwnd,end)
        api.SetCursorPos(*end)
        time.sleep(0.08)
    finally:
        api.mouse_event(0x0010,0,0,0,0)
    time.sleep(0.045)
