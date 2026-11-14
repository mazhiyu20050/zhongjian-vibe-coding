"""User-initiated native folder choice; no file scanning, uploading or execution."""
import threading

_lock=threading.Lock()


def choose_folder():
    if not _lock.acquire(blocking=False):raise ValueError('picker_open')
    root=None
    try:
        import tkinter
        from tkinter import filedialog
        root=tkinter.Tk();root.withdraw();root.attributes('-topmost',True)
        return filedialog.askdirectory(parent=root,title='选择项目源文件夹',mustexist=True) or None
    finally:
        if root is not None:root.destroy()
        _lock.release()
