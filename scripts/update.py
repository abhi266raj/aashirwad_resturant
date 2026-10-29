#!/usr/bin/env python3
"""Read a Google Sheet via temporary CSV download, cache images, and update the static site."""
import argparse
import csv
import io
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
AUTH_DIR = ROOT / '.google-auth'
TEMP_DIR = ROOT / 'temp'
CONFIG_PATH = Path(__file__).with_name('config.json')

FIELDS = ['id', 'name', 'category', 'price', 'diet', 'description', 'popular', 'image', 'sort_priority']
TRUTHY = {'yes', 'true', '1'}
FALSEY = {'no', 'false', '0'}

# Cards reach about 400 CSS pixels at the two-column breakpoint.
# Export at 2x density; the layout displays them in a 4:3 frame.
MENU_IMAGE_MAX_WIDTH = 800
MENU_IMAGE_MAX_HEIGHT = 600
MENU_IMAGE_QUALITY = 78


def load_config(path=CONFIG_PATH):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def default_sheet_url():
    return load_config()['sheet']['url']


def spreadsheet_id(value):
    value = (value or '').strip()
    if not value:
        raise ValueError('set sheet.url in scripts/config.json or provide --sheet-url')
    if value.startswith('https://'):
        parsed = urlparse(value)
        if parsed.netloc != 'docs.google.com':
            raise ValueError('sheet URL must be on docs.google.com')
        match = re.fullmatch(r'/spreadsheets/d/([A-Za-z0-9_-]+)(?:/.*)?', parsed.path)
        if not match:
            raise ValueError('invalid Google Sheet URL')
        return match.group(1)
    if re.fullmatch(r'[A-Za-z0-9_-]+', value):
        return value
    raise ValueError('invalid Google Sheet URL or ID')


def find_local_credentials_path():
    candidates = [
        AUTH_DIR / 'token.json',
        AUTH_DIR / 'credentials.json',
        AUTH_DIR / 'service-account.json',
        AUTH_DIR / 'service_account.json',
        AUTH_DIR / 'token-readonly.json',
        AUTH_DIR / 'token-editor.json',
        ROOT / 'credentials.json',
        ROOT / 'service-account.json',
        ROOT / 'service_account.json',
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def save_user_token(creds, path=AUTH_DIR / 'token.json'):
    """Permanently persist credentials to .google-auth/token.json with restricted permissions."""
    if not hasattr(creds, 'to_json'):
        return
    AUTH_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_file = path.with_suffix('.tmp')
    temp_file.write_text(creds.to_json(), encoding='utf-8')
    temp_file.replace(path)
    path.chmod(0o600)


def credentials_from_file(path, scopes):
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('type') == 'service_account':
        return service_account.Credentials.from_service_account_info(data, scopes=scopes)
    if data.get('type') == 'authorized_user' or 'refresh_token' in data:
        return Credentials.from_authorized_user_info(data, scopes=scopes)
    if 'installed' in data or 'web' in data:
        token_file = AUTH_DIR / 'token.json'
        if token_file.is_file():
            try:
                creds = Credentials.from_authorized_user_file(str(token_file), scopes=scopes)
                if creds and (creds.valid or creds.refresh_token):
                    return creds
            except Exception:
                pass
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_config(data, scopes=scopes)
            creds = flow.run_local_server(host='localhost', port=0, open_browser=True, timeout_seconds=300)
            save_user_token(creds, token_file)
            return creds
        except Exception as exc:
            raise RuntimeError(f'OAuth client sign-in failed: {exc}') from exc
    raise ValueError(f'Unrecognized credential format in {path}')


def find_credentials(scopes):
    # 0. Saved permanent user token in .google-auth/token.json
    token_file = AUTH_DIR / 'token.json'
    if token_file.is_file():
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(str(token_file), scopes=scopes)
            if creds and (creds.valid or creds.refresh_token):
                return creds
        except Exception:
            pass

    # 1. Direct access token in shell environment
    shell_token = os.environ.get('GOOGLE_ACCESS_TOKEN', '').strip()
    if shell_token:
        from google.oauth2.credentials import Credentials
        return Credentials(token=shell_token, scopes=scopes)

    # 2. Service account JSON in shell environment
    service_account_env = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '').strip()
    if service_account_env:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_info(json.loads(service_account_env), scopes=scopes)

    # 3. Credentials file path in shell environment
    app_creds_env = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '').strip()
    if app_creds_env and Path(app_creds_env).is_file():
        return credentials_from_file(Path(app_creds_env), scopes)

    # 4. User token JSON in shell environment
    user_token = os.environ.get('GOOGLE_OAUTH_TOKEN_JSON', '').strip()
    if user_token:
        from google.oauth2.credentials import Credentials
        return Credentials.from_authorized_user_info(json.loads(user_token), scopes=scopes)

    # 5. Local credential files in project
    local_file = find_local_credentials_path()
    if local_file:
        return credentials_from_file(local_file, scopes)

    # 6. Fetch from system gcloud user credentials if available and persist locally
    adc_file = Path.home() / '.config' / 'gcloud' / 'application_default_credentials.json'
    if adc_file.is_file():
        try:
            data = json.loads(adc_file.read_text(encoding='utf-8'))
            if data.get('type') == 'authorized_user' and 'refresh_token' in data:
                from google.oauth2.credentials import Credentials
                creds = Credentials.from_authorized_user_info(data)
                if creds:
                    save_user_token(creds)
                    return creds
        except Exception:
            pass

    # 7. Active gcloud credentials from shell
    try:
        import subprocess
        proc = subprocess.run(['gcloud', 'auth', 'print-access-token'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            from google.oauth2.credentials import Credentials
            return Credentials(token=proc.stdout.strip(), scopes=scopes)
    except Exception:
        pass

    # 8. Application Default Credentials (ADC)
    try:
        import google.auth
        creds, _ = google.auth.default(scopes=scopes)
        if creds and (getattr(creds, 'service_account_email', None) or hasattr(creds, 'signer')):
            return creds
        if creds and getattr(creds, 'scopes', None):
            if all(s in creds.scopes for s in scopes):
                return creds
    except Exception:
        pass

    return None


def login_with_browser(scopes):
    """Convenient, low-friction browser sign-in with permanent token saving."""
    import shutil
    import subprocess

    # 1. Prefer OAuth client credentials if present
    candidates = [
        AUTH_DIR / 'client.json',
        AUTH_DIR / 'credentials.json',
        ROOT / 'credentials.json',
    ]
    for client_file in candidates:
        if client_file.is_file():
            try:
                data = json.loads(client_file.read_text(encoding='utf-8'))
                if 'installed' in data or 'web' in data:
                    print('\nOpening browser for Google sign-in via OAuth client...')
                    from google_auth_oauthlib.flow import InstalledAppFlow
                    flow = InstalledAppFlow.from_client_config(data, scopes=scopes)
                    creds = flow.run_local_server(host='localhost', port=0, open_browser=True, timeout_seconds=300)
                    save_user_token(creds)
                    print('✓ OAuth browser login successful. Credentials saved permanently.\n')
                    return creds
            except Exception as exc:
                print(f'OAuth browser login failed: {exc}')

    # 2. Try gcloud browser sign-in if gcloud is installed
    if shutil.which('gcloud'):
        print('\nOpening browser for Google sign-in via gcloud...')
        try:
            result = subprocess.run(['gcloud', 'auth', 'login', '--enable-gdrive-access', '--update-adc'])
            if result.returncode == 0:
                print('✓ Google authentication successful.\n')
                creds = find_credentials(scopes)
                if creds:
                    save_user_token(creds)
                return creds
        except Exception as exc:
            print(f'gcloud browser login failed: {exc}')

    return None


def authorized_session(scopes, interactive=True):
    """Return an authenticated AuthorizedSession using local, environment, or browser credentials."""
    try:
        from google.auth.transport.requests import AuthorizedSession, Request
        from google.auth.exceptions import RefreshError
    except ImportError as exc:
        raise RuntimeError('install requirements.txt before accessing Google Sheets') from exc

    creds = find_credentials(scopes)
    if not creds and interactive and sys.stdin.isatty():
        print('\nGoogle Sheets authorization is required.')
        try:
            choice = input('Open browser to sign in with your Google account? [Y/n]: ').strip().lower()
            if choice in ('', 'y', 'yes'):
                creds = login_with_browser(scopes)
        except (KeyboardInterrupt, EOFError):
            print('\nSign-in cancelled.')

    if not creds:
        if os.environ.get('GITHUB_ACTIONS') == 'true' or os.environ.get('CI', '').lower() in ('true', '1'):
            raise RuntimeError('GitHub/CI requires GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_OAUTH_TOKEN_JSON')
        raise RuntimeError(
            "Local authentication not configured. To authenticate without logging in every time:\n"
            "  1. Run 'python3 scripts/setup.py --credentials <file.json>' with a Service Account key or OAuth token, or\n"
            "  2. Place your credentials in .google-auth/credentials.json or .google-auth/token.json"
        )
    if hasattr(creds, 'refresh') and (not creds.valid or getattr(creds, 'expired', False)) and getattr(creds, 'refresh_token', None):
        try:
            creds.refresh(Request())
            save_user_token(creds)
        except RefreshError as exc:
            if 'restricted_client' in str(exc) and hasattr(creds, '_scopes'):
                creds._scopes = None
                try:
                    creds.refresh(Request())
                    save_user_token(creds)
                except RefreshError as retry_exc:
                    raise RuntimeError(f'Credential refresh failed: {retry_exc}') from retry_exc
            else:
                raise RuntimeError(f'Credential refresh failed: {exc}') from exc
    return AuthorizedSession(creds)


def clean_temp_files(file_path=None, temp_dir=TEMP_DIR):
    """Clean up downloaded CSV and temporary directory."""
    if file_path:
        path = Path(file_path)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    temp_path = Path(temp_dir)
    if temp_path.is_dir():
        for temp_file in temp_path.glob('menu_*.csv'):
            try:
                temp_file.unlink()
            except OSError:
                pass
        try:
            if not any(temp_path.iterdir()):
                temp_path.rmdir()
        except OSError:
            pass


def download_sheet_csv(sheet_url, tab, session=None, temp_dir=TEMP_DIR):
    """Download Google Sheet data as a CSV file in a temporary folder."""
    import requests
    tab = (tab or '').strip()
    if not tab:
        raise ValueError("Sheet tab name is required and cannot be empty. Specify --sheet-name or set sheet.name in scripts/config.json.")

    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '_', tab).strip('_') or 'data'
    target_path = temp_dir / f"menu_{slug}_{int(time.time() * 1000)}.csv"
    sheet_id = spreadsheet_id(sheet_url)

    # 1. When session is provided, check sheet metadata to confirm tab existence
    sheet_gid = None
    if session is not None:
        meta_url = (
            'https://sheets.googleapis.com/v4/spreadsheets/'
            + urllib.parse.quote(sheet_id, safe='')
            + '?fields=sheets.properties(sheetId,title)'
        )
        try:
            meta_resp = session.get(meta_url, timeout=30)
            if meta_resp.status_code == 200:
                sheets_info = meta_resp.json().get('sheets', [])
                tab_map = {
                    s.get('properties', {}).get('title'): s.get('properties', {}).get('sheetId')
                    for s in sheets_info if s.get('properties', {}).get('title')
                }
                if tab not in tab_map:
                    available = ', '.join(repr(t) for t in tab_map.keys()) if tab_map else 'none'
                    raise ValueError(f"Sheet tab {tab!r} was not found in spreadsheet {sheet_id!r}. Available tabs: {available}.")
                sheet_gid = tab_map[tab]
        except ValueError:
            raise
        except Exception:
            pass

    export_urls = []
    if sheet_gid is not None:
        export_urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={sheet_gid}")
    export_urls.extend([
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(tab)}",
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&sheet={urllib.parse.quote(tab)}",
    ])

    requester = session if session is not None else requests.Session()
    csv_written = False

    for url in export_urls:
        try:
            resp = requester.get(url, timeout=30, allow_redirects=True)
            if resp.status_code == 200:
                text = resp.text
                if 'Table does not exist' in text or 'INVALID_ARGUMENT' in text:
                    raise ValueError(f"Sheet tab {tab!r} does not exist in the spreadsheet.")
                first_line = text.splitlines()[0] if text.splitlines() else ''
                if any(f in first_line for f in ('id', 'name', 'category', 'price')) and '<html' not in text[:200].lower():
                    target_path.write_text(text, encoding='utf-8')
                    csv_written = True
                    break
        except ValueError:
            raise
        except Exception:
            pass

    if not csv_written:
        if session is None:
            raise RuntimeError(
                f"Sheet tab {tab!r} is not publicly exportable and local credentials are not configured. "
                "Run 'python3 scripts/setup.py --credentials <file.json>' or place credentials in .google-auth/credentials.json."
            )
        range_name = f"'{tab.replace(chr(39), chr(39)*2)}'!A:I"
        api_url = (
            'https://sheets.googleapis.com/v4/spreadsheets/'
            + urllib.parse.quote(sheet_id, safe='') + '/values/'
            + urllib.parse.quote(range_name, safe='') + '?valueRenderOption=UNFORMATTED_VALUE'
        )
        resp = session.get(api_url, timeout=30)
        if resp.status_code == 400:
            raise ValueError(f"Sheet tab {tab!r} was not found in spreadsheet {sheet_id!r} or could not be read; run create_schema.py to configure it")
        resp.raise_for_status()
        values = resp.json().get('values', [])
        if not values:
            raise ValueError(f"Sheet tab {tab!r} is empty")
        with target_path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            for row in values:
                writer.writerow(row)
        csv_written = True

    return target_path


def read_csv_rows(csv_path):
    """Read and validate rows from a CSV file."""
    with Path(csv_path).open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('CSV is missing required columns')
        headers = [str(h).strip() for h in reader.fieldnames if h]
        if len(headers) != len(set(headers)):
            raise ValueError('CSV header contains duplicate column names')
        missing = set(FIELDS) - set(headers)
        if missing:
            raise ValueError('CSV is missing columns: ' + ', '.join(sorted(missing)))
        rows = list(reader)
    if not rows:
        raise ValueError('menu has no dishes')
    return rows


def sheet_rows(sheet_url, tab, session=None):
    """Download sheet CSV to temp, parse rows, and clean up temp files."""
    temp_csv = download_sheet_csv(sheet_url, tab, session=session)
    try:
        return read_csv_rows(temp_csv)
    finally:
        clean_temp_files(temp_csv)


def cell_text(value):
    return '' if value is None else str(value).strip()


def boolean(value, field, row, default=False):
    value = str(value or '').strip().lower()
    if not value:
        return default
    if value in TRUTHY:
        return True
    if value in FALSEY:
        return False
    raise ValueError(f'row {row}: {field} must be Yes or No')


def safe_local_path(value, row):
    value = str(value or '').strip()
    if not value:
        return ''
    if not value.startswith('assets/') or '..' in Path(value).parts or '\\' in value or '"' in value or "'" in value:
        raise ValueError(f'row {row}: image must be a path under assets/')
    if not (SITE / value).resolve().is_relative_to(SITE.resolve()):
        raise ValueError(f'row {row}: image path escapes the site directory')
    if not (SITE / value).is_file():
        raise ValueError(f'row {row}: image does not exist: {value}')
    return value


def fallback_image(name, diet, local_image):
    if local_image:
        return local_image
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    folder = 'veg' if diet == 'veg' else 'nonveg'
    for extension in ('jpg', 'png', 'webp'):
        path = f'assets/{folder}/{slug}/dish.{extension}'
        if (SITE / path).is_file():
            return path
    return 'assets/placeholder.svg'


def extract_categories(rows):
    """Dynamically extract unique category names from sheet rows, preserving appearance order."""
    seen = set()
    categories = []
    for row in rows:
        cat = str(row.get('category') or '').strip()
        if cat and cat not in seen:
            seen.add(cat)
            categories.append(cat)
    return categories


def normalize(rows):
    items = []
    priorities = [int(cell_text(row.get('sort_priority'))) for row in rows if re.fullmatch(r'[0-9]+', cell_text(row.get('sort_priority')))]
    default_priority = max(priorities, default=0)
    for row_number, row in enumerate(rows, 2):
        if not any(str(v or '').strip() for v in row.values()):
            continue
        item_id = str(row.get('id') or '').strip()
        name = str(row.get('name') or '').strip()
        category = str(row.get('category') or '').strip()
        diet = str(row.get('diet') or '').strip().lower()
        description = str(row.get('description') or '').strip()
        if not name or not category:
            raise ValueError(f'row {row_number}: name and category are required')
        if diet not in ('veg', 'non-veg'):
            raise ValueError(f'row {row_number}: diet must be Veg or Non-Veg')
        price_text = str(row.get('price') or '').strip()
        if not re.fullmatch(r'[0-9]+', price_text) or int(price_text) <= 0:
            raise ValueError(f'row {row_number}: price must be a positive whole rupee amount')
        image_value = str(row.get('image') or '').strip()
        url = image_value if image_value.startswith(('http://', 'https://')) else ''
        if url:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError(f'row {row_number}: image must be a public HTTP(S) image URL')
        local_image = safe_local_path(image_value if not url else '', row_number)
        popular = boolean(row.get('popular'), 'popular', row_number)
        sort_text = cell_text(row.get('sort_priority'))
        if sort_text and not re.fullmatch(r'[0-9]+', sort_text):
            raise ValueError(f'row {row_number}: sort_priority must be a whole number')
        priority = int(sort_text) if sort_text else default_priority
        items.append({
            'id': item_id, 'name': name, 'category': category,
            'price': int(price_text), 'diet': diet, 'description': description,
            'popular': popular, 'image_url': url,
            'fallback_image': fallback_image(name, diet, local_image),
            'sort_priority': priority,
        })
    if not items:
        raise ValueError('menu has no dishes')
    items.sort(key=lambda item: item['sort_priority'])
    categories = extract_categories(rows)
    return {'version': 1, 'categories': categories, 'items': items}


def download_image(url, target, max_width=900, max_height=900, quality=78):
    """Keep sheet supplied images as optimized, same-origin static files."""
    import requests
    from PIL import Image, ImageOps, UnidentifiedImageError

    response = requests.get(url, stream=True, timeout=(10, 30), allow_redirects=True)
    response.raise_for_status()
    if not response.url.startswith(('http://', 'https://')):
        raise ValueError('image URL redirected to an unsupported protocol')
    chunks = []
    size = 0
    for chunk in response.iter_content(65536):
        size += len(chunk)
        if size > 15 * 1024 * 1024:
            raise ValueError('image exceeds 15 MB')
        chunks.append(chunk)
    try:
        image = Image.open(io.BytesIO(b''.join(chunks)))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError('URL did not return a supported image') from exc
    image = ImageOps.exif_transpose(image).convert('RGB')
    image.thumbnail((max_width, max_height))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    image.save(temporary, format='JPEG', quality=quality, optimize=True, progressive=True)
    temporary.replace(target)


def localize_images(payload, max_width=900, max_height=900, quality=78):
    for item in payload['items']:
        if item['image_url']:
            image_key = hashlib.sha256((item["name"] + item["image_url"]).encode()).hexdigest()[:24]
            path = f"assets/sheet/{image_key}.jpg"
            download_image(item['image_url'], SITE / path, max_width, max_height, quality)
            item['image'] = path
        else:
            item['image'] = item['fallback_image']
        del item['image_url']
    return payload


def clear_unused_assets(dry_run=False):
    """Remove only image assets absent from generated menu and site references."""
    referenced = set()
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.ico', '.avif'}
    def keep(value):
        if not isinstance(value, str) or value.startswith(('http:', 'https:', 'data:')):
            return
        path = (SITE / value.split('?', 1)[0].split('#', 1)[0]).resolve()
        if path.is_relative_to(SITE.resolve()):
            referenced.add(path)
    def walk(value):
        if isinstance(value, dict):
            for nested in value.values(): walk(nested)
        elif isinstance(value, list):
            for nested in value: walk(nested)
        elif isinstance(value, str): keep(value)
    menu = SITE / 'menu.json'
    if not menu.is_file():
        raise ValueError('menu.json is required before clearing assets')
    walk(json.loads(menu.read_text()))
    for path in SITE.rglob('*'):
        if path.suffix in {'.html', '.css', '.js'} and path.name != 'menu-snapshot.js':
            for value in re.findall(r"[\"']([^\"'<>\s]+\.(?:jpg|jpeg|png|webp|gif|svg|ico|avif)(?:\?[^\"'<>\s]*)?)[\"']", path.read_text()):
                keep(value)
    candidates = list((SITE / 'assets').rglob('*')) + list(SITE.glob('*'))
    removed = []
    for path in candidates:
        if path.is_file() and path.suffix.lower() in image_extensions and path.resolve() not in referenced:
            removed.append(path.relative_to(SITE).as_posix())
            if not dry_run: path.unlink()
    for path in sorted((SITE / 'assets').rglob('*'), reverse=True):
        if path.is_dir() and not any(path.iterdir()) and not dry_run: path.rmdir()
    print(('Would remove' if dry_run else 'Removed') + f' {len(removed)} unused image assets')
    for path in removed: print('  ' + path)
    return removed


def write_menu_files(payload, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {
        output: json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n',
        output.with_name('menu-snapshot.js'): 'window.MENU_SNAPSHOT = ' + json.dumps(payload, ensure_ascii=True) + ';\n',
    }
    for path, content in files.items():
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(path)


def format_phone_display(phone):
    """Format 10-digit Indian phone number as +91 XXXXX XXXXX."""
    digits = re.sub(r'\D', '', str(phone or ''))
    if len(digits) == 10:
        return f'+91 {digits[:5]} {digits[5:]}'
    if len(digits) == 12 and digits.startswith('91'):
        return f'+91 {digits[2:7]} {digits[7:]}'
    return str(phone)


def build_restaurant_payload(config):
    """Extract restaurant brand, whatsapp, other contact phones, and location from config."""
    rest = config.get('restaurant', {})
    name = rest.get('name') or config.get('restaurant_name') or 'aashirwad'
    tagline = rest.get('tagline') or rest.get('description') or 'Authentic food and fast home delivery.'
    wa_num = rest.get('whatsapp_number') or rest.get('whatsapp') or '7004230188'
    wa_clean = re.sub(r'\D', '', str(wa_num))
    if len(wa_clean) == 12 and wa_clean.startswith('91'):
        wa_clean = wa_clean[2:]
    wa_display = rest.get('whatsapp_display') or format_phone_display(wa_clean)

    loc = rest.get('location', {})
    location = {
        'city': loc.get('city') or 'Hazaribagh',
        'address': loc.get('address') or 'Near Bansilal Chowk / Kani Bazar Chowk, Munka Bagicha, Hazaribagh, Jharkhand - 825301',
        'landmark': loc.get('landmark') or 'Near Bansilal Chowk',
        'timings': loc.get('timings') or '10:30 AM – 10:30 PM (All 7 Days)',
        'googleMapsUrl': loc.get('google_maps_url') or loc.get('googleMapsUrl') or 'https://maps.google.com',
    }

    phones = []
    if wa_clean:
        phones.append({
            'number': wa_clean,
            'display': wa_display,
            'isWhatsApp': True,
        })

    raw_contacts = rest.get('other_contact_numbers') or rest.get('contact_numbers') or []
    for item in raw_contacts:
        if isinstance(item, dict):
            num = re.sub(r'\D', '', str(item.get('number', '')))
            if len(num) == 12 and num.startswith('91'):
                num = num[2:]
            disp = item.get('display') or format_phone_display(num)
            is_wa = bool(item.get('is_whatsapp', False) or item.get('isWhatsApp', False))
        else:
            num = re.sub(r'\D', '', str(item))
            if len(num) == 12 and num.startswith('91'):
                num = num[2:]
            disp = format_phone_display(num)
            is_wa = False
        if num and num != wa_clean and not any(p['number'] == num for p in phones):
            phones.append({
                'number': num,
                'display': disp,
                'isWhatsApp': is_wa,
            })

    return {
        'name': name,
        'tagline': tagline,
        'whatsappNumber': wa_clean,
        'whatsappDisplay': wa_display,
        'phones': phones,
        'location': location,
    }


def write_restaurant_files(config, site_dir=SITE):
    """Write restaurant metadata to site/restaurant-data.js and site/restaurant.json."""
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    payload = build_restaurant_payload(config)
    js_content = (
        '// Generated from scripts/config.json - Do not edit directly\n'
        'window.RESTAURANT_CONFIG = ' + json.dumps(payload, ensure_ascii=False, indent=2) + ';\n\n'
        '// Backward compatibility exports\n'
        'window.RESTAURANT_PHONES = window.RESTAURANT_CONFIG.phones;\n'
        'window.RESTAURANT_LOCATION = {\n'
        '  name: window.RESTAURANT_CONFIG.name,\n'
        '  address: window.RESTAURANT_CONFIG.location.address,\n'
        '  city: window.RESTAURANT_CONFIG.location.city,\n'
        '  timings: window.RESTAURANT_CONFIG.location.timings,\n'
        '  googleMapsUrl: window.RESTAURANT_CONFIG.location.googleMapsUrl\n'
        '};\n'
    )
    (site_dir / 'restaurant-data.js').write_text(js_content, encoding='utf-8')
    (site_dir / 'restaurant.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def deploy_to_github():
    """Commit any updated menu files and push to GitHub to trigger automatic deployment."""
    import subprocess
    try:
        proc = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(ROOT))
        if proc.returncode != 0:
            print("Not inside a git repository; skipping automatic deployment.")
            return False

        # Stage menu and restaurant metadata files
        subprocess.run(
            ['git', 'add', 'site/menu.json', 'site/menu-snapshot.js', 'site/assets/sheet', 'site/restaurant-data.js', 'site/restaurant.json', 'scripts/config.json'],
            check=False,
            cwd=str(ROOT)
        )

        # Check if changes are staged
        diff_proc = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=str(ROOT))
        if diff_proc.returncode != 0:
            commit_proc = subprocess.run(
                ['git', 'commit', '-m', 'Update menu and restaurant configuration from config.json'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(ROOT)
            )
            if commit_proc.returncode == 0:
                print("✓ Committed updated menu files to local git.")
            else:
                print(f"Git commit notice: {commit_proc.stderr.strip()}")

        # Push to remote
        print("Pushing updates to GitHub for automatic deployment...")
        push_proc = subprocess.run(
            ['git', 'push', 'origin', 'HEAD:main'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(ROOT)
        )
        if push_proc.returncode == 0:
            print("✓ Pushed to GitHub. Automatic deployment triggered at:")
            print("  https://abhi266raj.github.io/aashirwad_resturant/\n")
            return True
        else:
            print(f"Notice: Git push failed ({push_proc.stderr.strip()}). Local files were updated successfully.")
            return False
    except Exception as exc:
        print(f"Notice: Automatic deployment skipped ({exc}). Local files were updated successfully.")
        return False


def main():
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', type=Path, help='local CSV for preview or verification')
    parser.add_argument('--sheet-url', default=default_sheet_url(), help='Google Sheet URL or ID; defaults to scripts/config.json')
    parser.add_argument('--sheet-name', '--tab', '--name', dest='tab', default=config['sheet']['name'], help='sheet tab name; defaults to sheet.name in config.json')
    parser.add_argument('--output', type=Path, default=SITE / 'menu.json')
    parser.add_argument('--clear-unused-assets', action='store_true', help='manually remove unused local image assets without reading Google Sheets')
    parser.add_argument('--dry-run', action='store_true', help='preview asset cleanup without deleting files')
    parser.add_argument('--deploy', action='store_true', help='automatically commit and push updated menu to GitHub to trigger deployment')
    args = parser.parse_args()

    if args.clear_unused_assets:
        clear_unused_assets(args.dry_run)
        return

    from setup import ensure_runtime
    ensure_runtime()

    temp_csv = None
    try:
        if args.csv:
            csv_path = args.csv
        else:
            session = None
            try:
                session = authorized_session(['https://www.googleapis.com/auth/spreadsheets.readonly'])
            except Exception as e:
                pass
            print(f'Downloading menu CSV for tab {args.tab!r}...')
            temp_csv = download_sheet_csv(args.sheet_url, args.tab, session=session)
            csv_path = temp_csv
            print(f'Downloaded menu CSV to temporary file: {csv_path}')

        rows = read_csv_rows(csv_path)
        payload = localize_images(normalize(rows), MENU_IMAGE_MAX_WIDTH, MENU_IMAGE_MAX_HEIGHT, MENU_IMAGE_QUALITY)
        sheet_categories = payload.get('categories', [])
        if sheet_categories and sheet_categories != config.get('categories'):
            config['categories'] = sheet_categories
            save_config(config)
            print(f"Dynamically updated categories in config.json: {', '.join(sheet_categories)}")

        write_menu_files(payload, args.output)
        write_restaurant_files(config, SITE)
        print(f'Validated {len(payload["items"])} dishes and wrote {args.output}')
        print(f'Updated restaurant configuration in site/restaurant-data.js')

        if args.deploy:
            deploy_to_github()
    finally:
        clean_temp_files(temp_csv)
        if temp_csv:
            print('Cleaned up temporary CSV files.')


def format_google_error(exc):
    if hasattr(exc, 'response') and exc.response is not None:
        try:
            data = exc.response.json()
            error = data.get('error', {})
            details = error.get('details', [])
            reason = details[0].get('reason') if details else ''
            if reason == 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' or 'insufficient' in error.get('message', '').lower():
                return (
                    "Your active shell gcloud login lacks Google Drive/Sheets scope.\n"
                    "-> Run this command in your shell to authorize Sheets access:\n"
                    "     gcloud auth login --enable-gdrive-access --update-adc\n"
                    "   (Or place a Service Account key at .google-auth/credentials.json)"
                )
            if error.get('message'):
                return error['message']
        except Exception:
            pass
    return str(exc)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Menu sync failed: {format_google_error(exc)}', file=sys.stderr)
        sys.exit(1)

