"""Windows user-bound encrypted credentials for restartable local jobs."""
import ctypes
import json
import os
from pathlib import Path
from ctypes import wintypes


def location():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PaperScientist" / "credentials.bin"


def crypt(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Encrypted local credential storage currently requires Windows; use environment variables elsewhere")
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def load_credentials():
    path = location()
    if os.name != "nt" or not path.is_file():
        return {}
    return json.loads(crypt(path.read_bytes(), decrypt=True))


def save_credentials(values):
    if any(not k.endswith("_API_KEY") for k in values):
        raise ValueError("Only API key fields are supported")
    path = location()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**load_credentials(), **values}
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(crypt(json.dumps(merged).encode()))
    os.replace(temporary, path)
