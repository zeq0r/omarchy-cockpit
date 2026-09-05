#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -m unittest -v test_cockpit.py
omarchy plugin validate .
cockpit_imports=$(mktemp -d)
trap 'rm -rf -- "$cockpit_imports"' EXIT
ln -s /usr/share/omarchy/shell "$cockpit_imports/qs"
# These categories cannot resolve Quickshell's injected/dynamic QObject members
# and its QProcess enum metadata. Structural/import/type warnings remain enabled.
/usr/lib/qt6/bin/qmllint -I "$cockpit_imports" \
  --missing-property disable --signal-handler-parameters disable --unqualified disable \
  BarWidget.qml Panel.qml
