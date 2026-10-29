#!/usr/bin/env python3
"""Create or verify the private Menu tab, header, and dropdown options."""
import argparse
import csv
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

from update import FIELDS, authorized_session, spreadsheet_id, default_sheet_url, load_config, save_config, login_with_browser

ROOT = Path(__file__).resolve().parents[1]
API = 'https://sheets.googleapis.com/v4/spreadsheets'


def checked(response):
    response.raise_for_status()
    return response.json()


def sheet_range(tab, cells):
    return quote(f"'{tab.replace(chr(39), chr(39) * 2)}'!{cells}", safe='')


def existing_values(session, base, tab, cells):
    response = session.get(f'{base}/values/{sheet_range(tab, cells)}', timeout=30)
    return checked(response).get('values', [])


def set_values(session, base, tab, cells, values):
    response = session.put(
        f'{base}/values/{sheet_range(tab, cells)}',
        params={'valueInputOption': 'RAW'},
        json={'majorDimension': 'ROWS', 'values': values},
        timeout=30,
    )
    checked(response)


def create_schema(sheet_url=None, tab=None, seed=False, create_new=False):
    config = load_config()
    sheet_url = sheet_url if sheet_url is not None else config['sheet']['url']
    tab = (tab if tab is not None else config['sheet']['name'] or '').strip()
    if not tab:
        raise ValueError("Sheet tab name is required and cannot be empty. Specify --sheet-name or set sheet.name in scripts/config.json.")
    session = authorized_session(['https://www.googleapis.com/auth/spreadsheets'])
    if create_new or not sheet_url:
        created = checked(session.post(API, json={'properties': {'title': tab}, 'sheets': [{'properties': {'title': tab}}]}, timeout=30))
        sheet_url = created['spreadsheetUrl']
        print('Created spreadsheet: ' + sheet_url)
    sheet_id = spreadsheet_id(sheet_url)
    base = f'{API}/{quote(sheet_id, safe="")}'
    try:
        metadata = checked(session.get(base, params={'fields': 'sheets.properties'}, timeout=30))
    except Exception as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status_code == 403 and sys.stdin.isatty():
            print("\nYour current Google account authorization lacks Google Sheets permissions.")
            try:
                choice = input("Open browser to sign in and grant Sheets permission? [Y/n]: ").strip().lower()
                if choice in ('', 'y', 'yes'):
                    new_creds = login_with_browser(['https://www.googleapis.com/auth/spreadsheets'])
                    if new_creds:
                        from google.auth.transport.requests import AuthorizedSession
                        session = AuthorizedSession(new_creds)
                        metadata = checked(session.get(base, params={'fields': 'sheets.properties'}, timeout=30))
                        exc = None
            except (KeyboardInterrupt, EOFError):
                pass
        if exc is not None:
            if status_code == 404:
                print(f"Spreadsheet {sheet_id} was not found (404). Creating new spreadsheet...")
                created = checked(session.post(API, json={'properties': {'title': tab}, 'sheets': [{'properties': {'title': tab}}]}, timeout=30))
                sheet_url = created['spreadsheetUrl']
                sheet_id = spreadsheet_id(sheet_url)
                base = f'{API}/{quote(sheet_id, safe="")}'
                metadata = checked(session.get(base, params={'fields': 'sheets.properties'}, timeout=30))
                print('Created spreadsheet: ' + sheet_url)
            else:
                raise

    matches = [sheet for sheet in metadata.get('sheets', []) if sheet.get('properties', {}).get('title') == tab]
    tab_already_existed = bool(matches)
    if matches:
        tab_id = matches[0]['properties']['sheetId']
    else:
        print(f"Sheet tab {tab!r} not found in spreadsheet. Creating tab {tab!r}...")
        result = checked(session.post(f'{base}:batchUpdate', json={'requests': [{'addSheet': {'properties': {'title': tab, 'gridProperties': {'rowCount': 1000, 'columnCount': len(FIELDS)}}}}]}, timeout=30))
        tab_id = result['replies'][0]['addSheet']['properties']['sheetId']
        print(f"Created sheet tab {tab!r}.")
    header = existing_values(session, base, tab, 'A1:I1')
    if header and any(str(cell).strip() for cell in header[0]) and header[0] != FIELDS:
        raise ValueError('existing header differs from the menu schema; no cells were overwritten')
    if not header or not any(str(cell).strip() for cell in header[0]):
        set_values(session, base, tab, 'A1:I1', [FIELDS])
    requests = [
        {'updateSheetProperties': {'properties': {'sheetId': tab_id, 'gridProperties': {'frozenRowCount': 1}}, 'fields': 'gridProperties.frozenRowCount'}},
        {'repeatCell': {'range': {'sheetId': tab_id, 'startRowIndex': 0, 'endRowIndex': 1}, 'cell': {'userEnteredFormat': {'backgroundColor': {'red': 0.02, 'green': 0.31, 'blue': 0.23}, 'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True}}}, 'fields': 'userEnteredFormat'}},
    ]

    # Dynamically fetch any existing categories from Column C if tab already existed
    sheet_categories = []
    if tab_already_existed:
        try:
            col_c_values = existing_values(session, base, tab, 'C2:C')
            for r in col_c_values:
                if r and str(r[0]).strip():
                    c = str(r[0]).strip()
                    if c not in sheet_categories and c != FIELDS[2]:
                        sheet_categories.append(c)
        except Exception:
            pass

    categories = sheet_categories
    if not categories:
        template_csv = ROOT / 'data/menu-template.csv'
        if template_csv.is_file():
            try:
                with template_csv.open(newline='', encoding='utf-8-sig') as handle:
                    template_rows = list(csv.DictReader(handle))
                from update import extract_categories
                categories = extract_categories(template_rows)
            except Exception:
                pass
    if not categories:
        categories = [
            "Roti & Naan", "Veg Main Course", "Non-Veg Main Course", "Momos",
            "Biryani & Rice", "Chowmein & Fast Food", "Starters & Chilli", "Drinks & Desserts"
        ]

    for column, values in ((2, categories), (4, ['Veg', 'Non-Veg']), (6, ['Yes', 'No'])):
        requests.append({'setDataValidation': {'range': {'sheetId': tab_id, 'startRowIndex': 1, 'startColumnIndex': column, 'endColumnIndex': column + 1}, 'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': value} for value in values]}, 'strict': True, 'showCustomUi': True}}})
    formulas = {
        0: '=OR(A2="",AND(ISNUMBER(A2),A2>0,A2=INT(A2),COUNTIF(A$2:A,A2)=1))',
        3: '=OR(D2="",AND(ISNUMBER(D2),D2>0,D2=INT(D2)))',
        7: '=OR(H2="",REGEXMATCH(H2,"^(https?://[^ ]+|assets/[^ ]+)$"))',
        8: '=OR(I2="",AND(ISNUMBER(I2),I2>=0,I2=INT(I2)))',
    }
    for column, formula in formulas.items():
        requests.append({'setDataValidation': {'range': {'sheetId': tab_id, 'startRowIndex': 1, 'startColumnIndex': column, 'endColumnIndex': column + 1}, 'rule': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': formula}]}, 'strict': True}}})
    for start, end, width in ((0, 1, 130), (1, 2, 220), (2, 3, 190), (5, 6, 340), (7, 9, 280)):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': tab_id, 'dimension': 'COLUMNS', 'startIndex': start, 'endIndex': end}, 'properties': {'pixelSize': width}, 'fields': 'pixelSize'}})
    checked(session.post(f'{base}:batchUpdate', json={'requests': requests}, timeout=30))
    if seed:
        existing = existing_values(session, base, tab, 'A2:I')
        if existing:
            raise ValueError('sheet already contains dishes; --seed did not overwrite them')
        with (ROOT / 'data/menu-template.csv').open(newline='', encoding='utf-8-sig') as handle:
            rows = list(csv.DictReader(handle))
        values = [[int(row[field]) if field in ('id', 'price', 'sort_priority') and row.get(field, '') else row.get(field, '') for field in FIELDS] for row in rows]
        if values:
            set_values(session, base, tab, f'A2:I{len(values) + 1}', values)
    config['sheet'].update(url=sheet_url, name=tab)
    config.pop('categories', None)
    save_config(config)
    print(f'Menu schema ready on {sheet_url} (tab: {tab}): {len(FIELDS)} columns, Veg/Non-Veg and Yes/No dropdowns')


def main():
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument('--sheet-url', default=default_sheet_url(), help='Google Sheet URL or ID; defaults to scripts/config.json')
    parser.add_argument('--sheet-name', '--tab', '--name', dest='tab', default=config['sheet']['name'], help='tab to configure or create')
    parser.add_argument('--seed', action='store_true', help='add the 50 starter dishes only if the Menu tab is empty')
    parser.add_argument('--new', action='store_true', help='create a new spreadsheet instead of using the default link')
    args = parser.parse_args()
    from setup import ensure_runtime
    ensure_runtime()
    create_schema(args.sheet_url, args.tab, args.seed, args.new)


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
        print(f'Schema creation failed: {format_google_error(exc)}', file=sys.stderr)
        sys.exit(1)
