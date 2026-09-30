"""Native text clipboard for Fusion's embedded palette; standard library only."""
import ctypes
import subprocess
import sys
import time


def copy_text(text):
    if not isinstance(text, str) or not text or "\0" in text:
        raise ValueError("Clipboard text must be nonempty and contain no null characters.")
    if sys.platform == "win32":
        _copy_windows(text)
    elif sys.platform == "darwin":
        subprocess.run(["/usr/bin/pbcopy"], input=text.encode("utf-8"), check=True,
                       timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise RuntimeError("Native clipboard is unavailable on this platform.")


def _copy_windows(text):
    from ctypes import wintypes
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    # Explicit pointer signatures are essential in Fusion's 64-bit Python.
    signatures = (
        (user.GetActiveWindow, [], wintypes.HWND),
        (user.GetForegroundWindow, [], wintypes.HWND),
        (user.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
        (user.EmptyClipboard, [], wintypes.BOOL),
        (user.SetClipboardData, [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
        (user.CloseClipboard, [], wintypes.BOOL),
        (kernel.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], wintypes.HANDLE),
        (kernel.GlobalLock, [wintypes.HANDLE], ctypes.c_void_p),
        (kernel.GlobalUnlock, [wintypes.HANDLE], wintypes.BOOL),
        (kernel.GlobalFree, [wintypes.HANDLE], wintypes.HANDLE),
    )
    for function, args, result in signatures:
        function.argtypes, function.restype = args, result
    owner = user.GetActiveWindow() or user.GetForegroundWindow()
    if not owner: raise RuntimeError("No window is available to own the clipboard.")
    payload = text.encode("utf-16-le")+b"\0\0"
    handle = kernel.GlobalAlloc(0x0002, len(payload))  # GMEM_MOVEABLE
    if not handle: raise RuntimeError("Could not allocate clipboard text.")
    opened = False
    try:
        address = kernel.GlobalLock(handle)
        if not address: raise RuntimeError("Could not lock clipboard text.")
        try: ctypes.memmove(address, payload, len(payload))
        finally: kernel.GlobalUnlock(handle)
        for attempt in range(5):
            if user.OpenClipboard(owner):
                opened = True
                break
            if attempt < 4: time.sleep(0.02)
        if not opened: raise RuntimeError("The clipboard is busy. Use the selected text to copy manually.")
        if not user.EmptyClipboard(): raise RuntimeError("Could not open the clipboard for writing.")
        if not user.SetClipboardData(13, handle):  # CF_UNICODETEXT
            raise RuntimeError("Windows did not accept the clipboard text.")
        handle = None  # Successful SetClipboardData transfers memory ownership.
    finally:
        if opened: user.CloseClipboard()
        if handle: kernel.GlobalFree(handle)
