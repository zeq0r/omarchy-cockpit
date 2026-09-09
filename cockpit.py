#!/usr/bin/env python3
"""Omarchy Cockpit prototype. Python stdlib; Hyprland 0.56 Lua dispatch API."""
import argparse
import collections
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

DATA = Path(os.environ.get('COCKPIT_DATA_DIR', str(Path.home() / '.local/share/omarchy-cockpit')))


def hypr(*args, json_output=False):
    p = subprocess.run(['hyprctl', *(['-j'] if json_output else []), *args], capture_output=True, text=True, timeout=10)
    if p.returncode or (not json_output and p.stdout.strip() != 'ok' and args[0] == 'dispatch'):
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return json.loads(p.stdout) if json_output else p.stdout.strip()


def lua(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    # Decimal byte escapes work for arbitrary UTF-8, unlike JSON's unicode escapes.
    return '"' + ''.join(chr(c) if 32 <= c < 127 and c not in (34, 92) else '\\%03d' % c for c in str(value).encode()) + '"'


def dispatch(function, **fields):
    hypr('dispatch', 'hl.dsp.' + function + '({' + ','.join(k + '=' + lua(v) for k, v in fields.items()) + '})')


def layout(message):
    hypr('dispatch', 'hl.dsp.layout(' + lua(message) + ')')


def clients():
    return [c for c in hypr('clients', json_output=True) if c.get('mapped')]


def path_for(name):
    if not re.fullmatch(r'[\w -]{1,64}', name, re.UNICODE):
        raise ValueError('Name: 1–64 letters, numbers, spaces, hyphens or underscores.')
    return DATA / (name + '.json')


def atomic_json_write(path, value):
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=DATA,
                                         prefix='.' + path.name + '.', delete=False) as f:
            tmp = Path(f.name)
            os.chmod(tmp, 0o600)
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        directory = os.open(DATA, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass


def write(name, value):
    atomic_json_write(path_for(name), value)


def read(name):
    value = json.loads(path_for(name).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Invalid snapshot: expected a JSON object')
    if value.get('schema') != 1:
        raise ValueError('Unknown snapshot version')
    return value


def infer_tree(windows):
    """Recover a slicing floorplan by finding a cut crossing no rectangle."""
    if not windows:
        return None
    if len(windows) == 1:
        return windows[0]['slot']
    for axis in (0, 1):
        ordered = sorted(windows, key=lambda w: w['at'][axis])
        for i in range(1, len(ordered)):
            left, right = ordered[:i], ordered[i:]
            edge = max(w['at'][axis] + w['size'][axis] for w in left)
            if edge <= min(w['at'][axis] for w in right):
                return {'axis': axis, 'first': infer_tree(left), 'second': infer_tree(right)}
    raise ValueError('Windows do not form a supported Dwindle tree (overlap/groups/fullscreen).')


def first_leaf(tree):
    return tree if isinstance(tree, str) else first_leaf(tree['first'])


def terminal_cwd(pid):
    try:
        children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
        for child in children:
            try:
                return str(Path(f'/proc/{child}/cwd').resolve(strict=True))
            except OSError:
                pass
        return str(Path(f'/proc/{pid}/cwd').resolve(strict=True))
    except OSError:
        return str(Path.home())


def recipe(c, slot):
    klass = c['class']
    if klass == 'foot' or klass.startswith('cockpit.'):
        app_id = klass if re.fullmatch(r'cockpit\.[0-9a-f]{12}', klass) else 'cockpit.' + slot
        return ['foot', '--app-id=' + app_id, '--working-directory=' + terminal_cwd(c['pid'])], app_id
    if klass in ('google-chrome', 'chromium'):
        executable = next((p for p in ('google-chrome-stable', 'google-chrome', 'chromium') if shutil.which(p)), None)
        return ([executable, '--new-window'] if executable else []), klass
    return [], klass


def capture(name, workspace=None):
    selected = [c for c in clients()
                if not c['workspace']['name'].startswith('special:')
                and ((workspace is None and not c['class'].startswith('cockpit.test.'))
                     or (workspace is not None and c['workspace']['name'] == str(workspace)))]
    if not selected:
        raise ValueError('No windows to save; the existing snapshot is preserved.')
    monitors = hypr('monitors', json_output=True)
    by_id = {m['id']: m['name'] for m in monitors}
    windows = []
    for c in selected:
        slot = uuid.uuid4().hex[:12]
        argv, restore_class = recipe(c, slot)
        windows.append({**{k: c[k] for k in ('address', 'pid', 'class', 'title', 'at', 'size', 'floating', 'fullscreen', 'grouped', 'pinned')}, 'stableId': c.get('stableId'), 'slot': slot, 'workspace': c['workspace']['name'], 'monitor': by_id[c['monitor']], 'launch': argv, 'restore_class': restore_class})
    value = {'schema': 1, 'name': name, 'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'session': os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'), 'layout': hypr('getoption', 'general:layout', json_output=True).get('str'), 'monitors': monitors, 'windows': windows}
    write(name, value)
    return value


def match_windows(snapshot, live):
    matches, used = {}, set()
    same_session = snapshot['session'] == os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    # Reserve identities for every slot before any heuristic can adopt a window.
    for w in snapshot['windows']:
        candidates = [c for c in live if c['address'] not in used]
        exact = [c for c in candidates if same_session and c['address'] == w['address'] and c['pid'] == w['pid'] and c.get('stableId') == w.get('stableId')]
        if not exact:
            exact = [c for c in candidates if c['class'] == w['restore_class'] and w['restore_class'].startswith('cockpit.')]
        if len(exact) > 1:
            raise ValueError('Multiple matching windows for ' + w['class'] + '. Close duplicates or use an empty workspace after login.')
        if exact:
            matches[w['slot']] = exact[0]['address']
            used.add(exact[0]['address'])
    for w in snapshot['windows']:
        if w['slot'] in matches:
            continue
        candidates = [c for c in live if c['address'] not in used and c['class'] in (w['class'], w['restore_class'])]
        same_title = [c for c in candidates if c['title'] == w['title']]
        other_slots = [s for s in snapshot['windows'] if s['slot'] not in matches and s['class'] == w['class']]
        if len(same_title) == 1 and sum(s['title'] == w['title'] for s in other_slots) == 1:
            candidates = same_title
        elif candidates and (len(candidates) > 1 or len(other_slots) > 1):
            raise ValueError('Ambiguous window identity for ' + w['class'] + '. Multiple saved or open windows match.')
        if candidates:
            matches[w['slot']] = candidates[0]['address']
            used.add(candidates[0]['address'])
    return matches


def prepare(snapshot):
    if snapshot['layout'] != 'dwindle' or hypr('getoption', 'general:layout', json_output=True).get('str') != 'dwindle':
        raise ValueError('This alpha only restores Dwindle layouts.')
    if not hypr('getoption', 'dwindle:preserve_split', json_output=True).get('bool'):
        raise ValueError('Dwindle preserve_split must be enabled.')
    current_monitors = {m['name']: m for m in hypr('monitors', json_output=True)}
    saved_monitors = {m['name']: m for m in snapshot['monitors']}
    for w in snapshot['windows']:
        if w['fullscreen'] or w['grouped'] or w['pinned'] or w['workspace'].startswith('special:'):
            raise ValueError('Fullscreen, groups, pinned windows and special workspaces are not supported yet. Disable them and save again.')
        old, new = saved_monitors[w['monitor']], current_monitors.get(w['monitor'])
        if not new or any(old[k] != new[k] for k in ('width', 'height', 'scale', 'transform', 'reserved')):
            raise ValueError('Connect the same monitors with the saved resolution, scale and reserved panel space.')
        # Work with coordinates translated to the current monitor origin.
        w['at'] = [w['at'][i] + new[k] - old[k] for i, k in enumerate(('x', 'y'))]
    live = clients()
    matches = match_windows(snapshot, live)
    if any(c.get('fullscreen') or c.get('grouped') or c.get('pinned') for c in live if c['address'] in matches.values()):
        raise ValueError('Disable fullscreen, groups and pinning on the windows to restore.')
    target_ws = {w['workspace'] for w in snapshot['windows']}
    extras = [c for c in live if c['workspace']['name'] in target_ws and c['address'] not in matches.values()]
    if extras:
        raise ValueError('Extra windows are present on a target workspace. Move them first; Cockpit will not close them.')
    for w in snapshot['windows']:
        if w['slot'] not in matches and (not w['launch'] or not shutil.which(w['launch'][0])):
            raise ValueError('Missing launch command for ' + w['class'] + '. Open the app first or configure a recipe through the CLI.')
    groups = collections.defaultdict(list)
    for w in snapshot['windows']:
        if not w['floating']:
            groups[w['workspace']].append(w)
    trees = {ws: infer_tree(windows) for ws, windows in groups.items()}
    return matches, trees


def wait_client(address, floating):
    for _ in range(30):
        c = next((c for c in clients() if c['address'] == address), None)
        if c is None:
            raise RuntimeError('A window was closed during restoration.')
        if c['floating'] == floating:
            return
        time.sleep(.05)
    raise RuntimeError('Hyprland did not change the floating state.')


def set_float(address, value):
    c = next(c for c in clients() if c['address'] == address)
    if c['floating'] != value:
        dispatch('window.float', window='address:' + address)
        wait_client(address, value)


def restore(name, dry_run=False):
    snapshot = read(name)
    # Older snapshots could include scratchpads even though restoration has never
    # supported special workspaces. Keep their regular workspaces restorable.
    snapshot['windows'] = [w for w in snapshot['windows']
                           if not w['workspace'].startswith('special:')]
    if not snapshot['windows']:
        raise ValueError('No regular-workspace windows to restore; special workspaces are not supported.')
    matches, trees = prepare(snapshot)
    plan = [{'class': w['class'], 'workspace': w['workspace'], 'action': 'reuse' if w['slot'] in matches else 'start', 'launch': w['launch']} for w in snapshot['windows']]
    if dry_run:
        return {'ok': True, 'plan': plan, 'message': 'Ready: ' + str(len(plan)) + ' windows.'}
    original_focus = hypr('activewindow', json_output=True).get('address')
    original_monitors = hypr('monitors', json_output=True)
    if clients():
        capture('before-restore')
    try:
        for w in snapshot['windows']:
            if w['slot'] in matches:
                continue
            dispatch('focus', workspace=workspace_selector(w['workspace']))
            before = {c['address'] for c in clients()}
            subprocess.Popen(w['launch'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                found = [c for c in clients() if c['address'] not in before and c['class'] == w['restore_class']]
                if len(found) == 1:
                    matches[w['slot']] = found[0]['address']
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Could not identify the new window: ' + w['class'])
        for w in snapshot['windows']:
            address = matches[w['slot']]
            set_float(address, True)
            dispatch('window.move', window='address:' + address, workspace=workspace_selector(w['workspace']), follow=False)
        for ws in {w['workspace'] for w in snapshot['windows']}:
            monitor = next(w['monitor'] for w in snapshot['windows'] if w['workspace'] == ws)
            dispatch('workspace.move', workspace=workspace_selector(ws), monitor=monitor)
        def expand(tree):
            if isinstance(tree, str):
                return
            anchor, new = matches[first_leaf(tree['first'])], matches[first_leaf(tree['second'])]
            # One compositor request prevents focus races between these steps.
            hypr('eval', 'hl.dispatch(hl.dsp.focus({window=' + lua('address:' + anchor) + '})); hl.dispatch(hl.dsp.layout(' + lua('preselect ' + ('r' if tree['axis'] == 0 else 'd')) + ')); hl.dispatch(hl.dsp.window.float({window=' + lua('address:' + new) + '}))')
            wait_client(new, False)
            expand(tree['first'])
            expand(tree['second'])
        for tree in trees.values():
            set_float(matches[first_leaf(tree)], False)
            expand(tree)
        for w in snapshot['windows']:
            if w['floating']:
                dispatch('window.resize', window='address:' + matches[w['slot']], x=w['size'][0], y=w['size'][1], exact=True)
                dispatch('window.move', window='address:' + matches[w['slot']], x=w['at'][0], y=w['at'][1])
        # Correct one worst mismatch at a time; remeasure after every change.
        for _ in range(max(12, len(matches) * 8)):
            time.sleep(.07)
            live = {c['address']: c for c in clients()}
            candidates = [w for w in snapshot['windows'] if not w['floating']]
            if not candidates:
                break
            worst = max(candidates, key=lambda w: sum(abs(a-b) for a,b in zip(w['size'], live[matches[w['slot']]]['size'])))
            if max(abs(a-b) for a,b in zip(worst['size'], live[matches[worst['slot']]]['size'])) <= 1:
                break
            dispatch('window.resize', window='address:' + matches[worst['slot']], x=worst['size'][0], y=worst['size'][1], exact=True)
        time.sleep(.25)
        live = {c['address']: c for c in clients()}
        errors = []
        for w in snapshot['windows']:
            c = live[matches[w['slot']]]
            delta = max(abs(a-b) for a,b in zip(w['at'] + w['size'], c['at'] + c['size']))
            errors.append({'slot': w['slot'], 'class': w['class'], 'max_pixel_error': delta, 'workspace_ok': c['workspace']['name'] == w['workspace'], 'floating_ok': c['floating'] == w['floating']})
        exact = all(e['max_pixel_error'] <= 2 and e['workspace_ok'] and e['floating_ok'] for e in errors)
        result = {'ok': exact, 'windows': errors, 'message': ('Restored' if exact else 'Partially restored') + ': largest difference ' + str(max(e['max_pixel_error'] for e in errors)) + ' px.'}
        write_report(result)
        return result
    finally:
        layout('preselect n')
        for monitor in original_monitors:
            ws = monitor['activeWorkspace']['name']
            dispatch('focus', workspace=workspace_selector(ws))
        if original_focus and any(c['address'] == original_focus for c in clients()):
            dispatch('focus', window='address:' + original_focus)


def workspace_selector(name):
    return name if name.isdecimal() else 'name:' + name


def write_report(result):
    atomic_json_write(DATA / 'last-restore-report.json', result)


def catalog():
    result = []
    for path in DATA.glob('*.json'):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(value, dict) and value.get('schema') == 1 and isinstance(value.get('saved_at'), str):
                result.append(value)
        except (ValueError, OSError, TypeError):
            pass
    return sorted(result, key=lambda v: v['saved_at'], reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('save'); p.add_argument('name'); p.add_argument('--workspace')
    p = sub.add_parser('restore'); p.add_argument('name'); p.add_argument('--dry-run', action='store_true')
    sub.add_parser('list')
    p = sub.add_parser('show'); p.add_argument('name')
    p = sub.add_parser('recipe'); p.add_argument('name'); p.add_argument('slot'); p.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (DATA / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'save':
            if args.name in ('before-restore', 'last-restore-report'):
                raise ValueError('This name is reserved for restoration.')
            value = capture(args.name, args.workspace)
            result = {'ok': True, 'message': 'Saved: ' + args.name + ' · ' + str(len(value['windows'])) + ' windows', 'snapshot': value}
        elif args.command == 'restore':
            result = restore(args.name, args.dry_run)
        elif args.command == 'list':
            result = {'ok': True, 'snapshots': catalog()}
        elif args.command == 'show':
            result = read(args.name)
        else:
            value = read(args.name)
            window = next(w for w in value['windows'] if w['slot'] == args.slot)
            argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
            if not argv or not shutil.which(argv[0]):
                raise ValueError('Specify an existing program and its arguments.')
            window['launch'] = argv
            write(args.name, value)
            result = {'ok': True, 'message': 'Launch command saved.'}
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('ok', True) else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'ok': False, 'message': str(error)}, ensure_ascii=False))
        sys.exit(1)
