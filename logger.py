import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _log_dir():
    if hasattr(sys, '_MEIPASS'):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath('.')
    log_dir = os.path.join(base, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


enabled = True

_log_file = None


def _get_log_file():
    global _log_file
    if _log_file is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        _log_file = os.path.join(_log_dir(), f'log_{ts}.txt')
    return _log_file


def log(msg: str):
    if not enabled:
        return
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}\n'
    try:
        with open(_get_log_file(), 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def log_exception(msg: str):
    if not enabled:
        return
    log(f'ERROR: {msg}')
    tb = traceback.format_exc()
    if tb and tb.strip() != 'NoneType: None':
        log(f'TRACEBACK:\n{tb}')
