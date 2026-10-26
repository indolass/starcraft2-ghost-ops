"""Fast list of the processes by image name (Windows ToolHelp snapshot). `tasklist` took up to 25 s on this machine while the game was running; the snapshot takes milliseconds.
Only the names and ids are read; nothing is touched."""
import ctypes
import subprocess
from ctypes import wintypes


class _Entry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]


def pids_of(image):
    """Ids of the processes whose image name is `image` (case-insensitive)."""
    try:
        k = ctypes.windll.kernel32
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        h = k.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
        if not h or h == wintypes.HANDLE(-1).value:
            raise OSError('snapshot failed')
        e = _Entry()
        e.dwSize = ctypes.sizeof(_Entry)
        out = []
        ok = k.Process32FirstW(h, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == image.lower():
                out.append(int(e.th32ProcessID))
            ok = k.Process32NextW(h, ctypes.byref(e))
        k.CloseHandle(h)
        return out
    except Exception:  # noqa: BLE001 - the old way as the fallback
        text = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % image, '/FO', 'CSV', '/NH'], capture_output=True, text=True, creationflags=0x08000000).stdout
        res = []
        for line in text.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) > 1 and parts[0].strip('"').lower() == image.lower():
                try:
                    res.append(int(parts[1]))
                except ValueError:
                    pass
        return res
