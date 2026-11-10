"""Window-Specific Input and Output Stream for PokéLit.

Enables background bot operation without interfering with foreground laptop use:
- Output Stream (WindowCapture): Captures ONLY the specific window via Win32 PrintWindow
  (PW_RENDERFULLCONTENT), even when covered, obscured, or not in the foreground.
- Input Stream (WindowInput): Sends keystrokes directly to the target window handle
  via Win32 PostMessage (WM_KEYDOWN / WM_KEYUP), avoiding OS-wide SendInput.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import time
from typing import Optional
import numpy as np

# Ensure Windows DPI awareness so all Win32 APIs, GetClientRect, ClientToScreen, and PyAutoGUI use physical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# Win32 Constants
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
PW_RENDERFULLCONTENT = 0x00000002

# Virtual Key Mapping
VK_CODES = {
    "w": 0x57,
    "a": 0x41,
    "s": 0x53,
    "d": 0x44,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "r": 0x52,
    "space": 0x20,
    "enter": 0x0D,
    "esc": 0x1B,
}


def attach_desktop() -> None:
    """Ensure thread is attached to interactive desktop 'Default'."""
    try:
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def find_target_window(keyword: str = "pokelit") -> Optional[int]:
    """Find the HWND of the PokéLit game window, filtering out IDEs and editors."""
    attach_desktop()
    candidates: list[tuple[int, str]] = []

    def enum_cb(hwnd: int, _: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                # Must match keyword and avoid editors / chat apps
                if (keyword.lower() in title or "poké" in title) and not any(
                    x in title for x in ["visual studio code", "antigravity", "cursor", "pycharm"]
                ):
                    candidates.append((hwnd, buf.value))
        return True

    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_cb)
    user32.EnumWindows(cb, 0)

    # Prioritize windows mentioning survival game or survivor
    for h, title in candidates:
        if "survivor" in title.lower() or "survival" in title.lower():
            return h

    return candidates[0][0] if candidates else None


class WindowCapture:
    """Captures frames directly from a target window HWND, even when obscured."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def grab_bgr(self) -> np.ndarray:
        """Capture the target window as a BGR image array."""
        rect = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        if w <= 0 or h <= 0:
            user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

        if w <= 0 or h <= 0:
            raise RuntimeError(f"Window {self.hwnd:#x} has zero size or is minimized.")

        hdc_window = user32.GetDC(self.hwnd)
        if not hdc_window:
            raise RuntimeError(f"GetDC failed for window {self.hwnd:#x}")

        hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
        hbm = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
        old_bmp = gdi32.SelectObject(hdc_mem, hbm)

        try:
            # PrintWindow with PW_RENDERFULLCONTENT (0x02) copies the window backing store
            user32.PrintWindow(self.hwnd, hdc_mem, PW_RENDERFULLCONTENT)

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h  # Top-down bitmap
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

            raw = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
            return raw[:, :, :3].copy()
        finally:
            if old_bmp:
                gdi32.SelectObject(hdc_mem, old_bmp)
            if hbm:
                gdi32.DeleteObject(hbm)
            if hdc_mem:
                gdi32.DeleteDC(hdc_mem)
            if hdc_window:
                user32.ReleaseDC(self.hwnd, hdc_window)


class WindowInput:
    """Direct window-targeted keyboard input using Win32 PostMessage."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self.target_hwnd = self._resolve_target_hwnd()

    def _resolve_target_hwnd(self) -> int:
        """Find the child window that handles web input (RenderWidgetHostHWND), avoiding GPU surface windows."""
        children: list[int] = []
        my_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(self.hwnd, ctypes.byref(my_pid))

        def enum_cb(ch: int, _: int) -> bool:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(ch, buf, 256)
            # Only match the actual web render widget host, NOT Intermediate D3D Window (which is in GPU subprocess)
            if buf.value == "Chrome_RenderWidgetHostHWND":
                ch_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(ch, ctypes.byref(ch_pid))
                if ch_pid.value == my_pid.value:
                    children.append(ch)
            return True

        cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_cb)
        user32.EnumChildWindows(self.hwnd, cb, 0)

        return children[0] if children else self.hwnd

    def key_down(self, key_str: str, is_repeat: bool = False) -> None:
        """Send WM_KEYDOWN to target window."""
        vk = VK_CODES.get(key_str.lower(), ord(key_str.upper()))
        scan = user32.MapVirtualKeyW(vk, 0)
        lparam = 1 | (scan << 16)
        if is_repeat:
            lparam |= (1 << 30)  # Bit 30 = previous key state was down (typematic repeat)
        user32.PostMessageW(self.hwnd, WM_KEYDOWN, vk, lparam)
        if self.target_hwnd != self.hwnd and user32.IsWindow(self.target_hwnd):
            user32.PostMessageW(self.target_hwnd, WM_KEYDOWN, vk, lparam)

    def key_up(self, key_str: str) -> None:
        """Send WM_KEYUP to target window (posted twice to guarantee delivery under GPU render load)."""
        vk = VK_CODES.get(key_str.lower(), ord(key_str.upper()))
        scan = user32.MapVirtualKeyW(vk, 0)
        lparam = 1 | (scan << 16) | (1 << 30) | (1 << 31)
        user32.PostMessageW(self.hwnd, WM_KEYUP, vk, lparam)
        user32.PostMessageW(self.hwnd, WM_KEYUP, vk, lparam)
        if self.target_hwnd != self.hwnd and user32.IsWindow(self.target_hwnd):
            user32.PostMessageW(self.target_hwnd, WM_KEYUP, vk, lparam)
            user32.PostMessageW(self.target_hwnd, WM_KEYUP, vk, lparam)

    def tap(self, key_str: str, hold_duration: float = 0.08) -> None:
        """Send key down, wait, send key up to the specific window."""
        self.key_down(key_str)
        time.sleep(hold_duration)
        self.key_up(key_str)

    def client_to_screen(self, client_x: int, client_y: int) -> tuple[int, int]:
        """Convert window client coordinates to screen coordinates."""
        pt = wintypes.POINT(int(client_x), int(client_y))
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    def click(self, client_x: int, client_y: int) -> None:
        """Send WM_LBUTTONDOWN and WM_LBUTTONUP directly to target window at client coordinates."""
        lparam = (int(client_y) << 16) | (int(client_x) & 0xFFFF)
        user32.PostMessageW(self.target_hwnd, WM_LBUTTONDOWN, 0x0001, lparam)
        time.sleep(0.06)
        user32.PostMessageW(self.target_hwnd, WM_LBUTTONUP, 0x0000, lparam)
        if self.target_hwnd != self.hwnd:
            user32.PostMessageW(self.hwnd, WM_LBUTTONDOWN, 0x0001, lparam)
            time.sleep(0.06)
            user32.PostMessageW(self.hwnd, WM_LBUTTONUP, 0x0000, lparam)
