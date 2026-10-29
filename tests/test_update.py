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
        with self.assertRaisesRegex(ValueError, 'local_image'):
            normalize([row])
        row['image'] = ''
        row['image'] = '../menu.json'
        with self.assertRaisesRegex(ValueError, 'local_image'):
            normalize([row])


if __name__ == '__main__':
    unittest.main()
