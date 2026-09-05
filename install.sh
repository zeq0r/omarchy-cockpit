#!/usr/bin/env bash
set -euo pipefail
cockpit_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cockpit_target="$HOME/.config/omarchy/plugins/zeq0r.cockpit"
omarchy plugin validate "$cockpit_source"
mkdir -p "$cockpit_target" "$HOME/.local/bin"
if [[ -f "$HOME/.config/omarchy/shell.json" ]]; then
  cp -p "$HOME/.config/omarchy/shell.json" "$HOME/.config/omarchy/shell.json.cockpit-backup-$(date +%Y%m%d-%H%M%S)"
fi
for cockpit_file in manifest.json BarWidget.qml Panel.qml cockpit.py README.md README.da.md preview.png LICENSE; do
  if [[ "$cockpit_source" != "$cockpit_target" ]]; then
    install -m 644 "$cockpit_source/$cockpit_file" "$cockpit_target/$cockpit_file"
  fi
done
cat > "$HOME/.local/bin/omarchy-cockpit" <<'EOF'
#!/usr/bin/env bash
exec python3 "$HOME/.config/omarchy/plugins/zeq0r.cockpit/cockpit.py" "$@"
EOF
chmod 755 "$HOME/.local/bin/omarchy-cockpit"
omarchy plugin validate "$cockpit_target"
omarchy-shell shell rescanPlugins
omarchy plugin enable zeq0r.cockpit --section left
# This installed Quickshell version retains old QML components across rescans.
omarchy restart shell
