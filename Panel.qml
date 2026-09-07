import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "zeq0r.cockpit"
  manageIpc: false
  property var anchorItem: null
  property var hostWidget: null
  property var snapshots: []
  property var selected: null
  property string message: "Save your layout and restore it after a restart."
  property string action: ""
  property bool autoSave: false
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property string backend: Qt.resolvedUrl("cockpit.py").toString().replace(/^file:\/\//, "")

  function snapshotSummary() {
    if (!root.snapshots.length) return "No saved layouts yet. Name your current layout below to get started."
    return root.snapshots.length + (root.snapshots.length === 1 ? " saved layout. Select it to preview or restore." : " saved layouts. Select one to preview or restore.")
  }
  function saveNamedLayout() {
    var name = nameInput.text.trim()
    if (name.length && !worker.running) {
      root.run(["save", name])
      keyCatcher.forceActiveFocus()
    }
  }
  function run(args) {
    if (worker.running) return
    action = args[0]
    message = action === "list" ? "Loading saved layouts …"
      : action === "save" ? "Saving layout …"
      : args.indexOf("--dry-run") >= 0 ? "Checking restore requirements …"
      : "Restoring layout …"
    worker.command = ["python3", root.backend].concat(args)
    worker.running = true
  }
  function open() { root.run(["list"]); root.controller.show() }
  function close() { root.controller.hide() }
  function toggle() { if (root.opened) root.close(); else root.open() }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.hostWidget || root, direction)
    return false
  }
  Process {
    id: worker
    stdout: StdioCollector { id: output; waitForEnd: true }
    stderr: StdioCollector { id: errors; waitForEnd: true }
    onExited: function(code) {
      try {
        var result = JSON.parse(output.text)
        if (root.action === "list" && result.ok) {
          root.snapshots = result.snapshots
          var name = root.selected ? root.selected.name : ""
          root.selected = root.snapshots.find(function(s) { return s.name === name }) || root.snapshots[0] || null
          root.message = root.snapshotSummary()
        } else {
          root.message = result.message || (result.ok ? "Done." : "Cockpit could not complete that action.")
          if (result.snapshot) root.selected = result.snapshot
          if (root.action === "save" && result.ok) Qt.callLater(function() { root.run(["list"]) })
        }
      } catch (e) {
        root.message = errors.text.trim() || (code === 0
          ? "Cockpit returned an unreadable response."
          : "Cockpit could not complete that action (exit " + code + ").")
      }
    }
  }
  Timer {
    interval: 60000
    repeat: true
    running: root.autoSave
    onTriggered: if (!worker.running) root.run(["save", "auto-" + Math.floor(Date.now() / 60000) % 10])
  }
  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(470))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)
    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: nameInput.activeFocus
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (!root.snapshots.length) return
        var index = root.snapshots.findIndex(function(s) { return root.selected && s.name === root.selected.name })
        root.selected = root.snapshots[(index + (dy || dx) + root.snapshots.length) % root.snapshots.length]
      }
      onActivateRequested: if (root.selected) root.run(["restore", root.selected.name])
      onTextKey: function(text) {
        if (text === "s") { nameInput.forceActiveFocus(); nameInput.selectAll() }
        else if (text === "c" && root.selected) root.run(["restore", root.selected.name, "--dry-run"])
        else if (text === "r" && root.selected) root.run(["restore", root.selected.name])
        else if (text === "a") root.autoSave = !root.autoSave
      }
      Column {
        id: content
        width: parent.width
        spacing: Style.space(12)
        Text {
          text: "COCKPIT"
          color: root.foreground
          font.family: Style.font.family
          font.pixelSize: Style.font.subtitle
          font.bold: true
        }
        Text {
          width: parent.width
          text: root.message
          textFormat: Text.PlainText
          color: root.foreground
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }
        Row {
          spacing: Style.space(8)
          Column {
            spacing: Style.space(4)
            Text {
              text: "LAYOUT NAME"
              color: root.foreground; opacity: 0.65
              font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
            }
            Rectangle {
              width: Style.space(290); height: Style.space(36)
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, nameInput.activeFocus ? 0.08 : 0.03)
              border.color: root.foreground; border.width: nameInput.activeFocus ? 2 : 1
              radius: Style.cornerRadius
              TextInput {
                id: nameInput
                anchors.fill: parent; anchors.margins: Style.space(8)
                text: "My cockpit"; color: root.foreground
                font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
                selectByMouse: true; maximumLength: 64
                Accessible.name: "Layout name"
                Accessible.description: "Name used when saving the current window layout"
                onAccepted: root.saveNamedLayout()
                Keys.onEscapePressed: keyCatcher.forceActiveFocus()
              }
            }
          }
          Button {
            anchors.bottom: parent.bottom
            text: "Save"
            tooltipText: nameInput.text.trim().length ? "Save the current window layout" : "Enter a layout name first"
            Accessible.name: "Save layout"
            Accessible.description: tooltipText
            enabled: !worker.running && nameInput.text.trim().length > 0
            onClicked: root.saveNamedLayout()
          }
        }
        Flickable {
          width: parent.width
          height: Math.min(savedList.implicitHeight, Style.space(116))
          contentHeight: savedList.implicitHeight
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          flickableDirection: Flickable.VerticalFlick
          interactive: contentHeight > height
          Column {
            id: savedList
            width: parent.width
            spacing: Style.space(4)
            Repeater {
              model: root.snapshots
              Button {
                required property var modelData
                width: savedList.width
                text: (root.selected && root.selected.name === modelData.name ? "▸ " : "") + modelData.name + "  ·  " + modelData.windows.length + " windows"
                tooltipText: "Select “" + modelData.name + "” for preview"
                selected: root.selected && root.selected.name === modelData.name
                leftAlign: true
                Accessible.name: modelData.name + ", " + modelData.windows.length + " windows"
                Accessible.description: selected ? "Selected layout" : "Select this layout for preview"
                onClicked: root.selected = modelData
              }
            }
          }
        }
        Flickable {
          width: parent.width
          height: Math.min(previews.implicitHeight, Style.space(240))
          contentHeight: previews.implicitHeight
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          flickableDirection: Flickable.VerticalFlick
          interactive: contentHeight > height
          Column {
            id: previews
            width: parent.width
            spacing: Style.space(8)
            Repeater {
              model: root.selected ? Array.from(new Set(root.selected.windows.map(function(w) { return w.workspace }))) : []
              Column {
                id: workspacePreview
                required property string modelData
                property var windows: root.selected ? root.selected.windows.filter(function(w) { return w.workspace === workspacePreview.modelData }) : []
                property var monitor: windows.length && root.selected ? root.selected.monitors.find(function(m) { return m.name === workspacePreview.windows[0].monitor }) : null
                width: previews.width
                spacing: Style.space(4)
                Text { text: "Workspace " + workspacePreview.modelData; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                Rectangle {
                  id: canvas
                  width: parent.width
                  height: Style.space(170)
                  color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.04)
                  radius: Style.cornerRadius
                  property real factor: workspacePreview.monitor ? Math.min(width / (workspacePreview.monitor.width / workspacePreview.monitor.scale), height / (workspacePreview.monitor.height / workspacePreview.monitor.scale)) : 0.1
                  Repeater {
                    model: workspacePreview.windows
                    Rectangle {
                      required property var modelData
                      x: (canvas.width - workspacePreview.monitor.width / workspacePreview.monitor.scale * canvas.factor) / 2 + (modelData.at[0] - workspacePreview.monitor.x) * canvas.factor
                      y: (modelData.at[1] - workspacePreview.monitor.y) * canvas.factor
                      width: modelData.size[0] * canvas.factor
                      height: modelData.size[1] * canvas.factor
                      color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.10)
                      border.color: root.foreground
                      radius: Style.cornerRadius
                      Text {
                        anchors.fill: parent; anchors.margins: Style.space(5)
                        text: modelData.class.startsWith("cockpit.") ? "Terminal" : modelData.class
                        textFormat: Text.PlainText
                        color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
                        elide: Text.ElideRight; wrapMode: Text.Wrap; clip: true
                      }
                    }
                  }
                }
              }
            }
          }
        }
        Row {
          spacing: Style.space(8)
          Button { text: "Check"; tooltipText: "Verify restore requirements without moving windows"; Accessible.name: "Check selected layout"; Accessible.description: tooltipText; enabled: root.selected !== null && !worker.running; onClicked: root.run(["restore", root.selected.name, "--dry-run"]) }
          Button { text: "Restore"; tooltipText: "Restore the selected window layout"; Accessible.name: "Restore selected layout"; Accessible.description: tooltipText; enabled: root.selected !== null && !worker.running; onClicked: root.run(["restore", root.selected.name]) }
          Button { text: root.autoSave ? "Auto: on" : "Auto: off"; tooltipText: root.autoSave ? "Stop one-minute rotating autosaves" : "Start one-minute rotating autosaves"; Accessible.name: "Automatic layout saving"; Accessible.description: tooltipText; Accessible.checked: root.autoSave; selected: root.autoSave; enabled: !worker.running; onClicked: root.autoSave = !root.autoSave }
        }
        Text {
          width: parent.width
          text: "S name/save · C check · R or Enter restore · ↑↓ select · A autosave · Esc close\nAlpha · Dwindle · same monitor setup\nAutosave runs every minute while the widget is loaded. Layouts include windows and terminal folders—not tabs, documents, or processes."
          color: root.foreground; opacity: 0.65
          font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }
      }
    }
  }
}
