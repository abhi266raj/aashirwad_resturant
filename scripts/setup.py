#!/usr/bin/env python3
"""Prepare an isolated Python environment once and reuse it on later runs."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / '.venv'
PYTHON = ENVIRONMENT / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
CHECK = 'import google.auth, requests, PIL'


def environment_ready(python):
    if not python.exists():
        return False
    return subprocess.run([str(python), '-c', CHECK], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def prepare():
    if environment_ready(PYTHON):
        return PYTHON
    if not PYTHON.exists():
        print('Creating project Python environment...', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(ENVIRONMENT)], check=True)
    print('Installing required packages...', flush=True)
    subprocess.run([str(PYTHON), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
    if not environment_ready(PYTHON):
        raise RuntimeError('Dependency verification failed')
    return PYTHON


def ensure_runtime():
    try:
        import google.auth
        import requests
        import PIL
        return
    except ImportError:
        pass
    python = prepare()
    result = subprocess.run([str(python), str(Path(sys.argv[0]).resolve()), *sys.argv[1:]])
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    try:
        python = prepare()
        print(f'Setup passed. Environment: {python}')
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'Setup failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
