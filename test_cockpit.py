import copy
import json
import os
from pathlib import Path
import tempfile
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


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_patch = patch.object(c, 'DATA', Path(self.tempdir.name) / 'data')
        self.data_patch.start()
        self.addCleanup(self.data_patch.stop)

    def test_write_is_atomic_private_and_leaves_no_temporary_file(self):
        value = {'schema': 1, 'name': 'Work', 'saved_at': '2026-09-07', 'windows': []}
        c.write('Work', value)
        path = c.DATA / 'Work.json'
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), value)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(c.DATA.glob('.Work.json.*')), [])

    def test_failed_write_preserves_snapshot_and_cleans_up(self):
        original = {'schema': 1, 'name': 'Work', 'saved_at': 'old', 'windows': []}
        c.write('Work', original)
        with patch.object(c.json, 'dump', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                c.write('Work', {'schema': 1})
        self.assertEqual(c.read('Work'), original)
        self.assertEqual(list(c.DATA.glob('.Work.json.*')), [])

    def test_write_syncs_file_and_parent_directory(self):
        real_fsync = c.os.fsync
        synced = []
        with patch.object(c.os, 'fsync', side_effect=lambda fd: (synced.append(fd), real_fsync(fd))[1]):
            c.write('Work', {'schema': 1})
        self.assertEqual(len(synced), 2)

    def test_write_report_creates_data_directory(self):
        c.write_report({'ok': False, 'message': 'partial'})
        path = c.DATA / 'last-restore-report.json'
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['message'], 'partial')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_read_rejects_non_object_snapshot(self):
        c.DATA.mkdir(parents=True)
        (c.DATA / 'bad.json').write_text('[]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'expected a JSON object'):
            c.read('bad')

    def test_catalog_skips_malformed_schema_one_entries(self):
        c.DATA.mkdir(parents=True)
        (c.DATA / 'missing-date.json').write_text('{"schema": 1}', encoding='utf-8')
        (c.DATA / 'array.json').write_text('[]', encoding='utf-8')
        c.write('valid', {'schema': 1, 'name': 'valid', 'saved_at': '2026-09-07'})
        self.assertEqual([item['name'] for item in c.catalog()], ['valid'])


if __name__ == '__main__':
    unittest.main()
