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

    def test_duplicate_app_classes_choose_deterministically(self):
        self.saved['windows'][0].update(workspace='1', at=[0, 0], size=[100, 100])
        live = [
            {'address': 'far', 'class': 'foot', 'title': 'shell', 'workspace': {'name': '2'}, 'at': [500, 0], 'size': [100, 100]},
            {'address': 'near', 'class': 'foot', 'title': 'shell', 'workspace': {'name': '1'}, 'at': [10, 0], 'size': [100, 100]},
        ]
        self.assertEqual(c.match_windows(self.saved, live), {'a': 'near'})

    def test_unique_restore_id_survives_title_change(self):
        live = [{'address': '0x2', 'class': 'cockpit.a', 'title': 'changed'}]
        self.assertEqual(c.match_windows(self.saved, live), {'a': '0x2'})

    def test_missing_slot_cannot_steal_surviving_identity(self):
        saved = copy.deepcopy(self.saved)
        saved['windows'].append({**saved['windows'][0], 'slot': 'b', 'address': '0x2', 'pid': 11, 'stableId': 'two', 'restore_class': 'cockpit.b'})
        live = [{'address': '0x2', 'pid': 11, 'stableId': 'two', 'class': 'foot', 'title': 'shell'}]
        with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='old'):
            self.assertEqual(c.match_windows(saved, live), {'b': '0x2'})

    def test_one_live_window_for_two_saved_slots_is_reused_once(self):
        saved = copy.deepcopy(self.saved)
        saved['windows'].append({**saved['windows'][0], 'slot': 'b', 'restore_class': 'cockpit.b'})
        for item in saved['windows']:
            item['workspace'] = '1'
        live = [{'address': '0x2', 'class': 'foot', 'title': 'changed',
                 'workspace': {'name': '2'}}]
        self.assertEqual(c.match_windows(saved, live), {'a': '0x2'})

    def test_same_class_slots_are_matched_by_unique_workspace(self):
        saved = copy.deepcopy(self.saved)
        saved['windows'][0]['workspace'] = '1'
        saved['windows'].append({**saved['windows'][0], 'slot': 'b', 'workspace': '2',
                                 'restore_class': 'foot', 'title': 'other'})
        live = [{'address': '0x2', 'class': 'foot', 'title': 'changed',
                 'workspace': {'name': '2'}}]
        self.assertEqual(c.match_windows(saved, live), {'b': '0x2'})


class SnapshotScopeTests(unittest.TestCase):
    def test_capture_ignores_special_workspaces(self):
        regular = {'class': 'foot', 'workspace': {'name': '1'}, 'monitor': 0}
        special = {'class': 'foot', 'workspace': {'name': 'special:scratchpad'}, 'monitor': 0}
        details = {'address': '0x1', 'pid': 1, 'title': 'shell', 'at': [0, 0],
                   'size': [100, 100], 'floating': False, 'fullscreen': 0,
                   'grouped': [], 'pinned': False, 'stableId': 'one'}
        monitor = {'id': 0, 'name': 'eDP-1'}
        with patch.object(c, 'clients', return_value=[{**details, **regular}, {**details, **special}]), \
             patch.object(c, 'hypr', side_effect=[[monitor], {'str': 'dwindle'}]), \
             patch.object(c, 'recipe', return_value=(['foot'], 'cockpit.one')), \
             patch.object(c, 'write') as write:
            snapshot = c.capture('Work')
        self.assertEqual([w['workspace'] for w in snapshot['windows']], ['1'])
        write.assert_called_once()

    def test_restore_ignores_special_workspaces_from_older_snapshot(self):
        snapshot = {'windows': [
            {'workspace': 'special:scratchpad', 'slot': 'special'},
            {'workspace': '2', 'slot': 'regular', 'class': 'foot', 'launch': ['foot']},
        ]}
        with patch.object(c, 'read', return_value=snapshot), \
             patch.object(c, 'prepare', return_value=({'regular': '0x1'}, {})) as prepare:
            result = c.restore('Work', dry_run=True)
        self.assertEqual(result['plan'], [{'class': 'foot', 'workspace': '2',
                                          'action': 'reuse', 'launch': ['foot']}])
        self.assertEqual([w['slot'] for w in prepare.call_args.args[0]['windows']], ['regular'])

    def test_restore_rejects_snapshot_with_only_special_workspaces(self):
        snapshot = {'windows': [{'workspace': 'special:scratchpad'}]}
        with patch.object(c, 'read', return_value=snapshot):
            with self.assertRaisesRegex(ValueError, 'No regular-workspace windows'):
                c.restore('Work', dry_run=True)


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
