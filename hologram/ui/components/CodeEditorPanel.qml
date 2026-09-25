import QtQuick
import QtQuick.Controls
import "../theme"

// Editor kode sederhana di dalam aplikasi: pohon folder proyek di kiri, isi file di kanan.
// Bukan IDE penuh -- tanpa penyorotan sintaks, tanpa tab banyak file -- cukup untuk melihat dan
// mengubah satu file lalu menyimpannya, tanpa pindah ke VS Code.
Rectangle {
    id: root
    radius: Theme.radius
    color: Theme.cardSolid
    border.color: Theme.line
    border.width: 1

    property string currentPath: ""
    property string savedText: ""
    readonly property bool hasFile: currentPath !== ""
    readonly property bool dirty: hasFile && area.text !== savedText

    function openAt(path, content) {
        root.currentPath = path
        root.savedText = content
        area.text = content
        status.text = ""
    }

    function save() {
        if (!root.hasFile) return
        editor.saveFile(root.currentPath, area.text)
    }

    Connections {
        target: editor
        function onFileOpened(path, content) { root.openAt(path, content) }
        function onFileSaved(path) { root.savedText = area.text; status.text = "Tersimpan"; statusTimer.restart() }
        function onErrorOccurred(message) { status.text = message; statusTimer.restart() }
    }
    Timer { id: statusTimer; interval: 3200; onTriggered: status.text = "" }

    Shortcut { sequence: "Ctrl+S"; onActivated: root.save() }

    // Header: judul, path file aktif + titik "belum tersimpan", tombol simpan, tombol tutup panel.
    Item {
        id: head
        height: Theme.px(40)
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: Theme.px(10) }

        Txt {
            anchors { left: parent.left; verticalCenter: parent.verticalCenter }
            text: "EDITOR KODE"
            font.bold: true
            font.pixelSize: Theme.fsBody
            font.letterSpacing: Theme.px(0.5)
            color: Theme.ink
        }
        Row {
            anchors.centerIn: parent
            spacing: Theme.px(6)
            visible: root.hasFile
            Txt { text: root.currentPath; font.pixelSize: Theme.fsSmall; color: Theme.muted; anchors.verticalCenter: parent.verticalCenter }
            Rectangle {
                visible: root.dirty
                width: Theme.px(7); height: width; radius: width / 2
                color: Theme.warn
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        Row {
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            spacing: Theme.px(10)
            Txt { id: status; text: ""; font.pixelSize: Theme.fsSmall; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
            ToggleButton {
                text: "Simpan"
                checked: root.dirty
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.save()
            }
        }
    }
    Rectangle {
        id: divider
        anchors { top: head.bottom; left: parent.left; right: parent.right; margins: Theme.px(10) }
        height: 1
        color: Theme.line
    }

    Row {
        anchors { top: divider.bottom; topMargin: Theme.px(8); left: parent.left; right: parent.right; bottom: parent.bottom; margins: Theme.px(10) }
        spacing: Theme.px(10)

        // Kiri: pohon file
        Rectangle {
            width: Math.min(Theme.px(260), parent.width * 0.32)
            height: parent.height
            radius: Theme.radiusSmall
            color: Theme.tint
            border.color: Theme.line
            border.width: 1

            ScrollView {
                anchors.fill: parent
                anchors.margins: Theme.px(6)
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                FileTreeItem {
                    id: tree
                    name: editor.rootName
                    path: ""
                    isDir: true
                    depth: 0
                    activePath: root.currentPath
                    onOpenFile: (p) => editor.openFile(p)
                    Component.onCompleted: { expanded = true; children = editor.listDir("") }
                }
            }
        }

        // Kanan: isi file
        Rectangle {
            width: parent.width - Theme.px(270)
            height: parent.height
            radius: Theme.radiusSmall
            color: Theme.tint
            border.color: Theme.line
            border.width: 1

            Txt {
                visible: !root.hasFile
                anchors.centerIn: parent
                text: "Pilih file di sebelah kiri untuk mulai mengedit."
                color: Theme.dim
                font.pixelSize: Theme.fsSmall
            }

            ScrollView {
                visible: root.hasFile
                anchors.fill: parent
                anchors.margins: Theme.px(10)
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AsNeeded

                TextArea {
                    id: area
                    objectName: "codeEditorArea"
                    wrapMode: TextArea.NoWrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsBody
                    color: Theme.text
                    selectionColor: Theme.tintStrong
                    selectedTextColor: Theme.text
                    background: null
                    persistentSelection: true
                }
            }
        }
    }
}
