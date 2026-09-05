import copy
import os
import unittest
from unittest.mock import patch
import cockpit as c


def window(slot, x, y, width, height):
    return {'slot': slot, 'at': [x, y], 'size': [width, height]}


class GeometryTests(unittest.TestCase):
    def test_nested_columns(self):
        tree = c.infer_tree([window('a', 0, 0, 600, 500), window('b', 0, 508, 600, 500), window('c', 608, 0, 1200, 1008)])
        self.assertEqual(tree, {'axis': 0, 'first': {'axis': 1, 'first': 'a', 'second': 'b'}, 'second': 'c'})

    def test_overlapping_layout_rejected(self):
        with self.assertRaises(ValueError):
            c.infer_tree([window('a', 0, 0, 100, 100), window('b', 50, 50, 100, 100)])

    def test_four_quadrants_and_shifted_origin(self):
        tree = c.infer_tree([window(str(i), 3440 + (i // 2) * 500, (i % 2) * 500, 490, 490) for i in range(4)])
        self.assertEqual(tree['axis'], 0)
        self.assertEqual(c.first_leaf(tree['second']), '2')

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            c.path_for('../test')

    def test_lua_unicode_and_quotes(self):
        self.assertEqual(c.lua('"\\\nø'), '"\\034\\092\\010\\195\\184"')


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.saved = {'session': 'old', 'windows': [{'slot': 'a', 'address': '0x1', 'pid': 10, 'stableId': 'one', 'class': 'foot', 'restore_class': 'cockpit.a', 'title': 'shell'}]}

    def test_address_reuse_after_reboot_not_identity(self):
        live = [{'address': '0x1', 'pid': 10, 'stableId': 'one', 'class': 'other', 'title': 'other'}]
        with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='new'):
            self.assertEqual(c.match_windows(self.saved, live), {})

    def test_ambiguous_terminals_rejected(self):
        live = [{'address': str(i), 'class': 'foot', 'title': 'shell'} for i in range(2)]
        with self.assertRaises(ValueError):
            c.match_windows(self.saved, live)

    def test_unique_restore_id_survives_title_change(self):
        live = [{'address': '0x2', 'class': 'cockpit.a', 'title': 'changed'}]
        self.assertEqual(c.match_windows(self.saved, live), {'a': '0x2'})

    def test_missing_slot_cannot_steal_surviving_identity(self):
        saved = copy.deepcopy(self.saved)
        saved['windows'].append({**saved['windows'][0], 'slot': 'b', 'address': '0x2', 'pid': 11, 'stableId': 'two', 'restore_class': 'cockpit.b'})
        live = [{'address': '0x2', 'pid': 11, 'stableId': 'two', 'class': 'foot', 'title': 'shell'}]
        with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='old'):
            self.assertEqual(c.match_windows(saved, live), {'b': '0x2'})

    def test_one_ambiguous_live_window_for_two_saved_slots_rejected(self):
        saved = copy.deepcopy(self.saved)
        saved['windows'].append({**saved['windows'][0], 'slot': 'b', 'restore_class': 'cockpit.b'})
        with self.assertRaises(ValueError):
            c.match_windows(saved, [{'address': '0x2', 'class': 'foot', 'title': 'shell'}])


if __name__ == '__main__':
    unittest.main()
