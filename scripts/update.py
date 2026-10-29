#!/usr/bin/env python3
"""Read a private Google Sheet, cache its images, and update the static site."""
import argparse
import csv
import io
import hashlib
import json
import os
import re
import sys
import urllib.parse
from urllib.parse import urlparse
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name('config.json')

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


def authorized_session(scopes):
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise RuntimeError('install requirements.txt before accessing Google Sheets') from exc
    user_token = os.environ.get('GOOGLE_OAUTH_TOKEN_JSON', '').strip()
    if user_token:
        from google.oauth2.credentials import Credentials
        return AuthorizedSession(Credentials.from_authorized_user_info(json.loads(user_token), scopes=scopes))
    credentials_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '').strip()
    if not credentials_json:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON is required')
    info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return AuthorizedSession(credentials)


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
FIELDS = ['id','name','category','price','diet','description','popular','image','sort_priority']
TRUTHY = {'yes', 'true', '1'}
FALSEY = {'no', 'false', '0'}


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
    return {'version': 1, 'items': items}


def sheet_rows(sheet_url, tab):
    sheet_id = spreadsheet_id(sheet_url)
    session = authorized_session(['https://www.googleapis.com/auth/spreadsheets.readonly'])
    range_name = f"'{tab.replace(chr(39), chr(39)*2)}'!A:I"
    url = ('https://sheets.googleapis.com/v4/spreadsheets/'
           + urllib.parse.quote(sheet_id, safe='') + '/values/'
           + urllib.parse.quote(range_name, safe='') + '?valueRenderOption=UNFORMATTED_VALUE')
    response = session.get(url, timeout=30)
    if response.status_code == 400:
        raise ValueError(f'Sheet tab {tab!r} was not found or could not be read; run create_schema.py locally to create/configure it')
    response.raise_for_status()
    values = response.json().get('values', [])
    if not values:
        raise ValueError('sheet is empty')
    headers = [str(v).strip() for v in values[0]]
    if len(headers) != len(set(headers)):
        raise ValueError('sheet header contains duplicate column names')
    missing = set(FIELDS) - set(headers)
    if missing:
        raise ValueError('sheet is missing columns: ' + ', '.join(sorted(missing)))
    rows = [dict(zip(headers, cells + [''] * (len(headers)-len(cells)))) for cells in values[1:]]
    return rows


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


# Cards reach about 400 CSS pixels at the two-column breakpoint.
# Export at 2x density; the layout displays them in a 4:3 frame.
MENU_IMAGE_MAX_WIDTH = 800
MENU_IMAGE_MAX_HEIGHT = 600
MENU_IMAGE_QUALITY = 78

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


def main():
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', type=Path, help='local CSV for preview or verification')
    parser.add_argument('--sheet-url', default=default_sheet_url(), help='Google Sheet URL or ID; defaults to scripts/config.json')
    parser.add_argument('--sheet-name', '--tab', '--name', dest='tab', default=config['sheet']['name'], help='sheet tab name; defaults to sheet.name in config.json')
    parser.add_argument('--output', type=Path, default=SITE / 'menu.json')
    parser.add_argument('--clear-unused-assets', action='store_true', help='manually remove unused local image assets without reading Google Sheets')
    parser.add_argument('--dry-run', action='store_true', help='preview asset cleanup without deleting files')
    args = parser.parse_args()
    if args.clear_unused_assets:
        clear_unused_assets(args.dry_run)
        return
    from setup import ensure_runtime
    ensure_runtime()
    if args.csv:
        with args.csv.open(newline='', encoding='utf-8-sig') as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or set(FIELDS) - set(reader.fieldnames):
                raise ValueError('CSV is missing required columns')
            rows = list(reader)
    else:
        rows = sheet_rows(args.sheet_url, args.tab)
    payload = localize_images(normalize(rows), MENU_IMAGE_MAX_WIDTH, MENU_IMAGE_MAX_HEIGHT, MENU_IMAGE_QUALITY)
    write_menu_files(payload, args.output)
    print(f'Validated {len(payload["items"])} dishes and wrote {args.output}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Menu sync failed: {exc}', file=sys.stderr)
        sys.exit(1)
