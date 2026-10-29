#!/usr/bin/env python3
"""Prepare the Python environment and local authentication for Google Sheets."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / '.venv'
PYTHON = ENVIRONMENT / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
AUTH_DIR = ROOT / '.google-auth'
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


def check_auth_status():
    """Detect configured Google credentials and return (is_configured, description)."""
    if os.environ.get('GOOGLE_ACCESS_TOKEN'):
        return True, 'Environment variable GOOGLE_ACCESS_TOKEN (from shell)'
    if os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'):
        return True, 'Environment variable GOOGLE_SERVICE_ACCOUNT_JSON (Service Account)'
    if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        return True, f'Environment variable GOOGLE_APPLICATION_CREDENTIALS ({path})'
    if os.environ.get('GOOGLE_OAUTH_TOKEN_JSON'):
        return True, 'Environment variable GOOGLE_OAUTH_TOKEN_JSON (OAuth Token)'

    candidates = [
        AUTH_DIR / 'token.json',
        AUTH_DIR / 'credentials.json',
        AUTH_DIR / 'service-account.json',
        AUTH_DIR / 'service_account.json',
        AUTH_DIR / 'token-readonly.json',
        AUTH_DIR / 'token-editor.json',
        AUTH_DIR / 'client.json',
        ROOT / 'credentials.json',
        ROOT / 'service-account.json',
        ROOT / 'service_account.json',
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                creds_type = data.get('type')
                if creds_type == 'service_account':
                    email = data.get('client_email', 'unknown')
                    return True, f'Local Service Account file ({path.name}: {email})'
                if creds_type == 'authorized_user' or 'refresh_token' in data:
                    return True, f'Local User Token ({path.name})'
                if 'installed' in data or 'web' in data:
                    return True, f'Local OAuth Client Secret ({path.name})'
                return True, f'Local credentials file ({path.name})'
            except Exception:
                pass

    try:
        proc = subprocess.run(['gcloud', 'auth', 'print-access-token'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            acc_proc = subprocess.run(['gcloud', 'config', 'get-value', 'account'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            account = acc_proc.stdout.strip() if acc_proc.returncode == 0 else 'active'
            return True, f'Shell gcloud active account ({account})'
    except Exception:
        pass

    try:
        import google.auth
        creds, project = google.auth.default()
        if creds:
            return True, f'Application Default Credentials (ADC: {project or "default"})'
    except Exception:
        pass

    return False, 'No local credentials configured'


def configure_credentials(file_path):
    """Import and securely store a local credentials JSON file."""
    source = Path(file_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Credentials file not found: {source}')
    try:
        content = source.read_text(encoding='utf-8')
        data = json.loads(content)
    except Exception as exc:
        raise ValueError(f'Invalid JSON credentials file: {exc}') from exc

    AUTH_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if data.get('type') == 'authorized_user' or 'refresh_token' in data:
        target = AUTH_DIR / 'token.json'
    else:
        target = AUTH_DIR / 'credentials.json'

    temporary = target.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(data, indent=2))
    temporary.replace(target)
    target.chmod(0o600)

    creds_type = data.get('type', 'OAuth client/token' if ('installed' in data or 'web' in data or 'refresh_token' in data) else 'credentials')
    client_info = data.get('client_email') or data.get('client_id') or ''
    print(f'Successfully configured local authentication:')
    print(f'  Target: {target}')
    print(f'  Type:   {creds_type}')
    if client_info:
        print(f'  Client: {client_info}')
    return target


def setup_auth_interactive():
    """Guide the user to set up local authentication."""
    print('\n--- Local Authentication Setup ---')
    configured, desc = check_auth_status()
    if configured:
        print(f'Current status: {desc}')
        choice = input('Do you want to replace existing credentials? [y/N]: ').strip().lower()
        if choice not in ('y', 'yes'):
            return

    print('\nTo authenticate with Google Sheets locally:')
    print('1. Use a Google Service Account JSON key (Recommended for simplicity):')
    print('   Download key from Google Cloud Console -> Service Accounts -> Keys')
    print('   and save it as: .google-auth/credentials.json')
    print('2. Or provide the path to your credentials file now:')

    try:
        path = input('Path to credentials JSON file (or press Enter to skip): ').strip()
        if path:
            configure_credentials(path)
        else:
            print(f'Skipped. You can also place credentials directly at: {AUTH_DIR / "credentials.json"}')
    except (EOFError, KeyboardInterrupt):
        print('\nSetup cancelled.')


def main():
    parser = argparse.ArgumentParser(description='Prepare Python environment and local authentication')
    parser.add_argument('--credentials', type=Path, help='path to Service Account or OAuth credentials JSON')
    parser.add_argument('--auth', action='store_true', help='set up or check local authentication')
    parser.add_argument('--check', action='store_true', help='check environment and authentication status')
    args = parser.parse_args()

    python = prepare()
    print(f'Environment: {python} (ready)')

    if args.credentials:
        configure_credentials(args.credentials)
        return

    configured, desc = check_auth_status()
    if args.auth:
        if sys.stdin.isatty():
            setup_auth_interactive()
        else:
            print(f'Local authentication: {desc}')
        return

    print(f'Local authentication: {desc}')
    if not configured:
        print("  -> Run 'python3 scripts/setup.py --credentials <file.json>' or place credentials in .google-auth/credentials.json")


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, FileNotFoundError) as exc:
        print(f'Setup failed: {exc}', file=sys.stderr)
        raise SystemExit(1)

