import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import create_schema
from update import FIELDS


def reply(payload):
    response = Mock()
    response.json.return_value = payload
    return response


class SchemaTests(unittest.TestCase):
    def test_configured_missing_tab_is_created_and_seeded_as_numbers(self):
        config = {'sheet': {'url': 'https://docs.google.com/spreadsheets/d/test/edit',
                           'name': 'Menu2', 'spreadsheet_title': 'Restaurant',
                           'categories': ['Roti & Naan']}}
        session = Mock()
        session.get.side_effect = [reply({'sheets': [{'properties': {'title': 'Menu', 'sheetId': 0}}]}),
                                   reply({}), reply({})]
        session.post.side_effect = [reply({'replies': [{'addSheet': {'properties': {'sheetId': 9}}}]}), reply({})]
        session.put.return_value = reply({})
        with patch.object(create_schema, 'load_config', return_value=copy.deepcopy(config)), \
             patch.object(create_schema, 'authorized_session', return_value=session), \
             patch.object(create_schema, 'save_config') as save:
            create_schema.create_schema(seed=True)
        add = session.post.call_args_list[0].kwargs['json']['requests'][0]
        self.assertEqual(add['addSheet']['properties']['title'], 'Menu2')
        self.assertTrue(all('Menu2' in call.args[0] for call in session.put.call_args_list))
        values = session.put.call_args_list[-1].kwargs['json']['values']
        self.assertIsInstance(values[0][FIELDS.index('id')], int)
        self.assertIsInstance(values[0][FIELDS.index('price')], int)
        rules = session.post.call_args_list[1].kwargs['json']['requests']
        dropdowns = [rule['setDataValidation'] for rule in rules if 'setDataValidation' in rule and rule['setDataValidation']['rule']['condition']['type'] == 'ONE_OF_LIST']
        self.assertEqual(len(dropdowns), 3)
        self.assertTrue(all(rule['rule']['strict'] for rule in dropdowns))
        self.assertEqual(save.call_args.args[0]['sheet']['name'], 'Menu2')

    def test_existing_tab_is_used_without_creating_another(self):
        config = {'sheet': {'url': 'test', 'name': 'Menu2', 'spreadsheet_title': 'Restaurant', 'categories': ['Rice']}}
        session = Mock()
        session.get.side_effect = [reply({'sheets': [{'properties': {'title': 'Menu2', 'sheetId': 7}}]}), reply({'values': [FIELDS]})]
        session.post.return_value = reply({})
        with patch.object(create_schema, 'load_config', return_value=config), patch.object(create_schema, 'authorized_session', return_value=session), patch.object(create_schema, 'save_config'):
            create_schema.create_schema()
        requests = session.post.call_args.kwargs['json']['requests']
        self.assertFalse(any('addSheet' in request for request in requests))
        self.assertFalse(session.put.called)


if __name__ == '__main__':
    unittest.main()
