"""Opt-in integration test: uses only disposable foot windows on a new workspace."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import cockpit as c


def main():
    original = c.hypr('activewindow', json_output=True).get('address')
    workspace = 'cockpit-test-' + str(os.getpid())
    prefix = 'cockpit.test.' + str(os.getpid())
    addresses = set()
    classes = set()
    reports = []
    c.DATA = Path(tempfile.mkdtemp(prefix='cockpit-live-'))
    try:
        c.dispatch('focus', workspace='name:' + workspace)
        for i in range(3):
            app_id = prefix + '.' + str(i)
            classes.add(app_id)
            subprocess.Popen(['foot', '--app-id=' + app_id, '--title=Cockpit test ' + str(i), 'sleep', '300'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                found = [w for w in c.clients() if w['class'] == app_id]
                if found:
                    addresses.add(found[0]['address'])
                    break
                time.sleep(.05)
            else:
                raise RuntimeError('Testterminalen startede ikke')
        time.sleep(.3)
        windows = sorted([w for w in c.clients() if w['address'] in addresses], key=lambda w: w['class'])
        for w in windows:
            c.set_float(w['address'], True)
        # Two left terminals with one wide right terminal, like the user's layout.
        c.set_float(windows[0]['address'], False)
        for anchor, new, direction in [(windows[0], windows[2], 'r'), (windows[0], windows[1], 'd')]:
            c.dispatch('focus', window='address:' + anchor['address'])
            c.layout('preselect ' + direction)
            c.set_float(new['address'], False)
        c.dispatch('window.resize', window='address:' + windows[0]['address'], x=649, y=519, exact=True)
        time.sleep(.3)
        snap = c.capture('test', workspace)
        classes.update(w['restore_class'] for w in snap['windows'])
        reports.append({'saved_geometry': [{'at': w['at'], 'size': w['size']} for w in snap['windows']]})
        # Scramble the original geometry before restoring.
        for w in windows:
            c.set_float(w['address'], True)
            c.dispatch('window.move', window='address:' + w['address'], x=3500, y=200)
        reports.append({'existing_windows': c.restore('test')})
        # All saved clients disappear; restore must launch and identify new clients.
        for address in addresses:
            c.dispatch('window.close', window='address:' + address)
        time.sleep(.3)
        snap['session'] = 'simulated-previous-login'
        c.write('test', snap)
        reports.append({'fresh_processes': c.restore('test')})
        # Probe a harder tree: both children of the root have their own split.
        current = sorted([w for w in c.clients() if w['class'] in classes], key=lambda w: w['class'])
        app_id = prefix + '.fourth'
        classes.add(app_id)
        subprocess.Popen(['foot', '--app-id=' + app_id, 'sleep', '300'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            fourth = next((w for w in c.clients() if w['class'] == app_id), None)
            if fourth:
                break
            time.sleep(.05)
        if not fourth:
            raise RuntimeError('Fjerde testterminal startede ikke')
        current.append(fourth)
        for w in current:
            c.set_float(w['address'], True)
        c.set_float(current[0]['address'], False)
        for a, b, direction in [(0, 2, 'r'), (0, 1, 'd'), (2, 3, 'd')]:
            c.dispatch('focus', window='address:' + current[a]['address'])
            c.layout('preselect ' + direction)
            c.set_float(current[b]['address'], False)
        c.dispatch('window.resize', window='address:' + current[0]['address'], x=649, y=400, exact=True)
        c.dispatch('window.resize', window='address:' + current[2]['address'], x=1249, y=650, exact=True)
        time.sleep(.3)
        c.capture('four', workspace)
        for w in current:
            c.set_float(w['address'], True)
        reports.append({'four_tiled_windows': c.restore('four')})
        c.set_float(fourth['address'], True)
        c.dispatch('window.move', window='address:' + fourth['address'], x=4400, y=250)
        c.dispatch('window.resize', window='address:' + fourth['address'], x=430, y=330, exact=True)
        time.sleep(.3)
        c.capture('floating', workspace)
        c.dispatch('window.move', window='address:' + fourth['address'], x=3500, y=50)
        reports.append({'mixed_floating_tiled': c.restore('floating')})
        assert reports[1]['existing_windows']['ok'], reports[1]
        assert reports[2]['fresh_processes']['ok'], reports[2]
        assert reports[3]['four_tiled_windows']['ok'], reports[3]
        assert reports[4]['mixed_floating_tiled']['ok'], reports[4]
    finally:
        for w in c.clients():
            if w['class'] in classes:
                c.dispatch('window.close', window='address:' + w['address'])
        if original and any(w['address'] == original for w in c.clients()):
            c.dispatch('focus', window='address:' + original)
        c.layout('preselect n')
        Path(__file__).with_name('live-test-results.json').write_text(json.dumps(reports, indent=2))
        print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
