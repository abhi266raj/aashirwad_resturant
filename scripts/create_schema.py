#!/usr/bin/env python3
"""Create or verify the private Menu tab, header, and dropdown options."""
import argparse
import csv
import os
import sys
from pathlib import Path
from urllib.parse import quote

from update import FIELDS, authorized_session, spreadsheet_id, default_sheet_url, load_config

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
        json={'range': f"'{tab}'!{cells}", 'majorDimension': 'ROWS', 'values': values},
        timeout=30,
    )
    checked(response)


def create_schema(sheet_url, tab='Menu', seed=False, name='aashirwad_resturant — Menu', create_new=False):
    session = authorized_session(['https://www.googleapis.com/auth/spreadsheets'])
    if create_new or not sheet_url:
        created = checked(session.post(API, json={'properties': {'title': name}, 'sheets': [{'properties': {'title': tab}}]}, timeout=30))
        sheet_url = created['spreadsheetUrl']
        print('Created spreadsheet: ' + sheet_url)
    sheet_id = spreadsheet_id(sheet_url)
    base = f'{API}/{quote(sheet_id, safe="")}'
    metadata = checked(session.get(base, params={'fields': 'sheets.properties'}, timeout=30))
    matches = [sheet for sheet in metadata.get('sheets', []) if sheet.get('properties', {}).get('title') == tab]
    if matches:
        tab_id = matches[0]['properties']['sheetId']
    else:
        result = checked(session.post(f'{base}:batchUpdate', json={'requests': [{'addSheet': {'properties': {'title': tab, 'gridProperties': {'rowCount': 1000, 'columnCount': len(FIELDS)}}}}]}, timeout=30))
        tab_id = result['replies'][0]['addSheet']['properties']['sheetId']
    header = existing_values(session, base, tab, 'A1:I1')
    if header and any(str(cell).strip() for cell in header[0]) and header[0] != FIELDS:
        raise ValueError('existing header differs from the menu schema; no cells were overwritten')
    if not header or not header[0]:
        set_values(session, base, tab, 'A1:I1', [FIELDS])
    requests = [
        {'updateSheetProperties': {'properties': {'sheetId': tab_id, 'gridProperties': {'frozenRowCount': 1}}, 'fields': 'gridProperties.frozenRowCount'}},
        {'repeatCell': {'range': {'sheetId': tab_id, 'startRowIndex': 0, 'endRowIndex': 1}, 'cell': {'userEnteredFormat': {'backgroundColor': {'red': 0.48, 'green': 0.18, 'blue': 0.13}, 'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True}}}, 'fields': 'userEnteredFormat'}},
    ]
    for column, values in ((2, load_config()['sheet']['categories']), (4, ['Veg', 'Non-Veg']), (6, ['Yes', 'No'])):
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
        values = [[row.get(field, '') for field in FIELDS] for row in rows]
        if values:
            set_values(session, base, tab, f'A2:I{len(values) + 1}', values)
    if create_new:
        config = load_config()
        config['sheet'].update(url=sheet_url, name=name, menu_tab=tab)
        (Path(__file__).with_name('config.json')).write_text(__import__('json').dumps(config, indent=2, ensure_ascii=False) + '\n')
    print(f'Menu schema ready: {len(FIELDS)} columns, Veg/Non-Veg and Yes/No dropdowns')


def main():
    from setup import ensure_runtime
    ensure_runtime()
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument('--sheet-url', default=default_sheet_url(), help='Google Sheet URL or ID; defaults to MENU_SHEET_URL')
    parser.add_argument('--tab', default=os.environ.get('MENU_SHEET_TAB', config['sheet']['menu_tab']))
    parser.add_argument('--seed', action='store_true', help='add the 50 starter dishes only if the Menu tab is empty')
    parser.add_argument('--name', default=config['sheet']['name'], help='title for a newly created spreadsheet')
    parser.add_argument('--new', action='store_true', help='create a new spreadsheet instead of using the default link')
    args = parser.parse_args()
    create_schema(args.sheet_url, args.tab, args.seed, args.name, args.new)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Schema creation failed: {exc}', file=sys.stderr)
        sys.exit(1)
