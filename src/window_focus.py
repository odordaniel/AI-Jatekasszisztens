"""Foreground activation for an explicitly opened Windows history window."""
import ctypes
from ctypes import wintypes
import logging
import os


def activate_window(hwnd, user32=None, kernel32=None):
    if user32 is None:
        if os.name != 'nt':
            return False
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    attached = False
    current_thread = foreground_thread = 0
    try:
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.AttachThreadInput.restype = wintypes.BOOL
        for name in ('BringWindowToTop', 'SetForegroundWindow', 'IsIconic'):
            function = getattr(user32, name)
            function.argtypes, function.restype = [wintypes.HWND], wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetFocus.argtypes, user32.SetFocus.restype = [wintypes.HWND], wintypes.HWND
        user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
        user32.ClipCursor.restype = wintypes.BOOL

        foreground = user32.GetForegroundWindow()
        current_thread = kernel32.GetCurrentThreadId()
        if foreground:
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
        if foreground_thread and foreground_thread != current_thread:
            attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE; otherwise preserve geometry.
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if user32.GetForegroundWindow() != hwnd:
            return False
        user32.SetFocus(hwnd)
        user32.ClipCursor(None)  # Release a game-confined pointer after taking focus.
        return True
    except (OSError, AttributeError, ValueError):
        logging.warning('Az előzményablak natív aktiválása sikertelen.')
        return False
    finally:
        if attached:
            try:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
            except OSError:
                logging.warning('Az ideiglenes beviteli kapcsolat bontása sikertelen.')
