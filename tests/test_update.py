import csv
import tempfile
import unittest
from unittest.mock import patch
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update
from update import FIELDS, normalize


class MenuSyncTests(unittest.TestCase):
    def setUp(self):
        with (Path(__file__).resolve().parents[1] / 'data/menu-template.csv').open(newline='') as handle:
            self.rows = list(csv.DictReader(handle))

    def test_ids_are_read_without_assignment_or_validation(self):
        rows = [self.rows[0].copy(), self.rows[1].copy()]
        rows[0]['id'] = 'sheet-owned-id'
        rows[1]['id'] = 'sheet-owned-id'
        self.assertEqual([item['id'] for item in normalize(rows)['items']], ['sheet-owned-id', 'sheet-owned-id'])

    def test_duplicate_sort_prioritys_preserve_ids(self):
        rows = [self.rows[1].copy(), self.rows[0].copy()]
        for row in rows: row['sort_priority'] = '10'
        items = normalize(rows)['items']
        self.assertEqual([item['name'] for item in items], ['Plain Naan', 'Makhan Roti'])
        self.assertEqual([item['id'] for item in items], ['2', '1'])

    def test_blank_priorities_follow_existing_maximum(self):
        rows = [self.rows[0].copy(), self.rows[1].copy(), self.rows[2].copy()]
        rows[0]['sort_priority'] = '100'
        rows[1]['sort_priority'] = ''
        rows[2]['sort_priority'] = ''
        self.assertEqual([item['sort_priority'] for item in normalize(rows)['items']], [100, 100, 100])

    def test_cleanup_keeps_referenced_images(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / 'assets').mkdir()
            for name in ['used.jpg', 'unused.jpg', 'placeholder.svg']:
                (site / 'assets' / name).write_text('image')
            (site / 'brand.svg').write_text('logo')
            (site / 'index.html').write_text('<img src="brand.svg?v=2">')
            (site / 'app.js').write_text("const fallback = 'assets/placeholder.svg';")
            (site / 'menu.json').write_text(json.dumps({'items': [{'image': 'assets/used.jpg'}]}))
            with patch.object(update, 'SITE', site):
                self.assertEqual(update.clear_unused_assets(True), ['assets/unused.jpg'])
                self.assertTrue((site / 'assets/unused.jpg').exists())
                self.assertEqual(update.clear_unused_assets(), ['assets/unused.jpg'])
            self.assertTrue((site / 'brand.svg').exists())
            self.assertTrue((site / 'assets/used.jpg').exists())
            self.assertTrue((site / 'assets/placeholder.svg').exists())

    def test_numeric_zero_priority_is_not_blank(self):
        rows = [self.rows[0].copy(), self.rows[1].copy(), self.rows[2].copy()]
        rows[0]['sort_priority'] = 0
        rows[1]['sort_priority'] = 10
        rows[2]['sort_priority'] = ''
        self.assertEqual([item['sort_priority'] for item in normalize(rows)['items']], [0, 10, 10])

    def test_snapshot_preserves_dish_text(self):
        payload = {'items': [{'name': '<Paneer> & "Rice"', 'description': 'Fresh \u2028 food'}]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'menu.json'
            update.write_menu_files(payload, output)
            self.assertEqual(json.loads(output.read_text()), payload)
            snapshot = output.with_name('menu-snapshot.js').read_text()
            self.assertEqual(json.loads(snapshot.removeprefix('window.MENU_SNAPSHOT = ').strip().removesuffix(';')), payload)

    def test_seed_and_added_dish(self):
        added = dict.fromkeys(FIELDS, '')
        added.update(id='51', name='Masala Fries', category='Snacks', price='95', diet='Veg',
                     description='Crispy fries', popular='No', image='https://example.com/fries.jpg',
                     available='Yes')
        payload = normalize(self.rows + [added])
        self.assertEqual(len(payload['items']), 51)
        self.assertEqual(payload['items'][-1]['category'], 'Snacks')
        self.assertEqual(payload['items'][-1]['image_url'], added['image'])
        self.assertEqual(payload['items'][-1]['fallback_image'], 'assets/placeholder.svg')

    def test_invalid_price_prevents_publish(self):
        bad = self.rows[0].copy()
        bad['price'] = '₹20'
        with self.assertRaisesRegex(ValueError, 'price'):
            normalize([bad])

    def test_diet(self):
        row = self.rows[0].copy()
        row['diet'] = 'Non-Veg'
        item = normalize([row])['items'][0]
        self.assertEqual(item['diet'], 'non-veg')

    def test_unsafe_image_rejected(self):
        row = self.rows[0].copy()
        row['image'] = 'javascript:alert(1)'
        with self.assertRaisesRegex(ValueError, 'image'):
            normalize([row])
        row['image'] = ''
        row['image'] = '../menu.json'
        with self.assertRaisesRegex(ValueError, 'image'):
            normalize([row])

    def test_download_sheet_csv_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str) / 'temp_sub'
            mock_session = unittest.mock.Mock()
            mock_resp = unittest.mock.Mock()
            mock_resp.status_code = 200
            # Return valid CSV header and row
            mock_resp.text = ','.join(FIELDS) + '\n1,Makhan Roti,Roti & Naan,20,Veg,Hot roti,No,,1\n'
            mock_session.get.return_value = mock_resp

            csv_file = update.download_sheet_csv('https://docs.google.com/spreadsheets/d/test-id/edit', 'Menu2', session=mock_session, temp_dir=temp_dir)
            self.assertTrue(csv_file.is_file())
            self.assertTrue(str(csv_file).startswith(str(temp_dir)))

            # Verify read_csv_rows parses it properly
            rows = update.read_csv_rows(csv_file)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['name'], 'Makhan Roti')

            # Verify clean_temp_files deletes file and directory
            update.clean_temp_files(csv_file, temp_dir=temp_dir)
            self.assertFalse(csv_file.exists())
            self.assertFalse(temp_dir.exists())

    def test_download_sheet_csv_api_fallback_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str) / 'temp_sub'
            mock_session = unittest.mock.Mock()
            export_fail = unittest.mock.Mock(status_code=403, text='Forbidden')
            api_success = unittest.mock.Mock(
                status_code=200,
                json=lambda: {'values': [FIELDS, ['1', 'Makhan Roti', 'Roti & Naan', '20', 'Veg', 'Hot roti', 'No', '', '1']]}
            )
            mock_session.get.side_effect = [export_fail, export_fail, api_success]

            csv_file = update.download_sheet_csv('https://docs.google.com/spreadsheets/d/test-id/edit', 'Menu2', session=mock_session, temp_dir=temp_dir)
            self.assertTrue(csv_file.is_file())

            rows = update.read_csv_rows(csv_file)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['name'], 'Makhan Roti')

            update.clean_temp_files(csv_file, temp_dir=temp_dir)
            self.assertFalse(csv_file.exists())

    def test_local_authentication_missing_message(self):
        with unittest.mock.patch.dict('os.environ', {}, clear=True), \
             unittest.mock.patch.object(update, 'find_local_credentials_path', return_value=None), \
             unittest.mock.patch('google.auth.default', side_effect=Exception('no ADC')):
            with self.assertRaisesRegex(RuntimeError, 'Local authentication not configured'):
                update.authorized_session(['https://www.googleapis.com/auth/spreadsheets.readonly'])

    def test_download_sheet_csv_fails_explicitly_on_error(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str) / 'temp_sub'
            mock_session = unittest.mock.Mock()
            export_fail = unittest.mock.Mock(status_code=403, text='Forbidden')
            api_fail = unittest.mock.Mock(status_code=403)
            import requests
            api_fail.raise_for_status.side_effect = requests.exceptions.HTTPError('403 Forbidden')
            mock_session.get.side_effect = [export_fail, export_fail, api_fail]

            with self.assertRaises(requests.exceptions.HTTPError):
                update.download_sheet_csv('https://docs.google.com/spreadsheets/d/test-id/edit', 'Menu2', session=mock_session, temp_dir=temp_dir)
            # Ensure no corrupted CSV was left
            self.assertFalse(any(temp_dir.glob('*.csv')))

    def test_download_sheet_csv_fails_when_unauthenticated_and_private(self):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str) / 'temp_sub'
            with unittest.mock.patch('requests.Session.get') as mock_get:
                mock_get.return_value = unittest.mock.Mock(status_code=403, text='Forbidden')
                with self.assertRaisesRegex(RuntimeError, 'local credentials are not configured'):
                    update.download_sheet_csv('https://docs.google.com/spreadsheets/d/test-id/edit', 'Menu2', session=None, temp_dir=temp_dir)


if __name__ == '__main__':
    unittest.main()
