"""Sandboxed Python execution (P36).

Runs short student code snippets in a **separate process** with:
  * no network (the child never imports/opens sockets in practice; we also block
    a denylist of dangerous modules at import time),
  * a CPU/wall-time limit (SIGALRM + subprocess timeout),
  * a memory cap (resource.RLIMIT_AS on POSIX),
  * captured stdout/stderr, truncated to a safe size.

This is *defense in depth*, not a security boundary on its own — for production,
run it inside a container/gVisor. The per-user isolation + time/mem caps make it
safe enough for a learning sandbox and keep one student from burning the host.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from typing import Any

# The child must NOT inherit the server's environment — it holds provider API
# keys, the JWT SECRET_KEY and the Supabase service key. Pass only a minimal env
# so a snippet like `import os; print(os.environ)` can't exfiltrate secrets.
_SAFE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "PYTHONIOENCODING": "utf-8",
    "LANG": os.environ.get("LANG", "C.UTF-8"),
}

MAX_OUTPUT = 10_000        # chars
DEFAULT_TIMEOUT = 6        # seconds
MEM_LIMIT_MB = 256

# Modules that would let snippets touch the network / filesystem / host.
# NOTE: "os" is blocked at the ROOT (the old "os.system" string never matched the
# import guard, so `import os; os.system(...)` was wide open). "importlib" is
# blocked too, else it bypasses this denylist entirely.
_BLOCKED = (
    "os", "socket", "subprocess", "shutil", "requests", "urllib", "urllib2",
    "httpx", "http", "ftplib", "smtplib", "telnetlib", "asyncio", "socketserver",
    "ctypes", "multiprocessing", "pty", "fcntl", "importlib", "webbrowser", "glob",
)

_HARNESS = '''
import resource, sys, builtins
# memory cap (address space)
try:
    _mb = {mem} * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (_mb, _mb))
except Exception:
    pass
# block dangerous imports
_BLOCKED = set({blocked!r})
_real_import = builtins.__import__
def _guard(name, *a, **k):
    root = name.split(".")[0]
    if root in _BLOCKED or name in _BLOCKED:
        raise ImportError("module '%s' is not allowed in the sandbox" % name)
    return _real_import(name, *a, **k)
builtins.__import__ = _guard

import signal
def _timeout(signum, frame):
    raise TimeoutError("execution timed out")
try:
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm({timeout})
except Exception:
    pass

_CODE = {code!r}
try:
    exec(compile(_CODE, "<snippet>", "exec"), {{"__name__": "__main__"}})
except Exception as e:
    import traceback
    traceback.print_exc()
'''


def run_python(code: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Execute ``code`` in an isolated subprocess. Returns stdout/stderr/ok."""
    if len(code) > 20_000:
        return {"ok": False, "stdout": "", "stderr": "Snippet too long (20k char limit)."}

    harness = _HARNESS.format(
        mem=MEM_LIMIT_MB, blocked=list(_BLOCKED),
        timeout=max(1, min(timeout, 15)), code=textwrap.dedent(code),
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", harness],
            capture_output=True, text=True,
            timeout=max(2, min(timeout, 15)) + 2,
            env=_SAFE_ENV,            # scrub secrets from the child's environment
        )
        out = (proc.stdout or "")[:MAX_OUTPUT]
        err = (proc.stderr or "")[:MAX_OUTPUT]
        return {"ok": proc.returncode == 0 and not err, "stdout": out, "stderr": err}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Execution timed out."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stdout": "", "stderr": f"Sandbox error: {e}"}
