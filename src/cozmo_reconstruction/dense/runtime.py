"""Discover a pinned CUDA Python binding or official native COLMAP executable."""

import ctypes
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

VERSION = "4.2.1"


def cuda_device_available():
    try:
        driver = ctypes.CDLL("nvcuda.dll" if os.name == "nt" else "libcuda.so.1")
        count = ctypes.c_int()
        return (
            driver.cuInit(0) == 0
            and driver.cuDeviceGetCount(ctypes.byref(count)) == 0
            and count.value > 0
        )
    except (OSError, AttributeError):
        return False


def executable_path():
    configured = os.getenv("COLMAP_EXECUTABLE")
    if configured:
        return Path(configured).expanduser().resolve()
    found = shutil.which("colmap")
    if found:
        return Path(found).resolve()
    # Optional project-local installation; wheels can instead use PATH or the env setting.
    candidate = Path.cwd() / ".tools/colmap/bin/colmap.exe"
    return candidate.resolve() if os.name == "nt" and candidate.is_file() else None


@lru_cache(maxsize=8)
def _probe_executable(path, size, modified):
    """Cache only the executable's build identity, never GPU availability."""
    try:
        result = subprocess.run(
            [path, "-h"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        output = result.stdout + result.stderr
        return (
            result.returncode == 0
            and re.search(r"COLMAP\s+4\.2\.1(?:\s|\()", output) is not None
            and "with CUDA" in output
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def runtime_status():
    try:
        import pycolmap as pc
    except ImportError:
        return {"available": False, "backend": None, "reason": "Install the reconstruct extra."}
    if pc.__version__ != VERSION:
        return {"available": False, "backend": None, "reason": "PyCOLMAP 4.2.1 is required."}
    if pc.has_cuda:
        compiled, backend = True, "pycolmap_cuda"
    else:
        path = executable_path()
        compiled = False
        if path and path.is_file():
            stat = path.stat()
            compiled = _probe_executable(str(path), stat.st_size, stat.st_mtime_ns)
        backend = "colmap_executable"
    if not compiled:
        return {
            "available": False,
            "backend": None,
            "reason": "Install official COLMAP 4.2.1 with CUDA and set COLMAP_EXECUTABLE. The Python package is CPU-only.",
        }
    if not cuda_device_available():
        return {"available": False, "backend": backend, "reason": "No usable NVIDIA CUDA device."}
    return {"available": True, "backend": backend, "reason": None}
