import QtQuick
import QtQuick.Shapes
import "../theme"

// Satu baris di pohon file: folder (bisa dibuka/tutup) atau file (bisa diklik untuk dibuka di editor).
// Anak folder dimuat sekali saat pertama dibuka, lewat editor.listDir(path).
//
// Catatan teknis: QML tidak mengizinkan sebuah tipe memakai dirinya sendiri langsung sebagai delegate
// (dianggap "instantiated recursively"), jadi anak folder dimuat lewat Loader dengan URL berkas ini,
// bukan lewat menulis "FileTreeItem { ... }" langsung di dalam berkas FileTreeItem.qml sendiri.
Column {
    id: root
    property string name: ""
    property string path: ""
    property bool isDir: false
    property int depth: 0
    property string activePath: ""     // path file yang sedang terbuka di editor, untuk menyorot barisnya
    signal openFile(string path)

    property bool expanded: false
    property var children: []

    width: parent ? parent.width : 0

    function toggle() {
        if (!root.isDir) { root.openFile(root.path); return }
        root.expanded = !root.expanded
        if (root.expanded && root.children.length === 0) {
            root.children = editor.listDir(root.path)
        }
    }

    Rectangle {
        id: row
        width: root.width
        height: Theme.px(24)
        radius: Theme.px(5)
        readonly property bool active: !root.isDir && root.path === root.activePath
        color: area.containsMouse ? Theme.tintStrong : active ? Theme.tint : "transparent"

        Row {
            anchors { left: parent.left; leftMargin: Theme.px(6) + root.depth * Theme.px(14); verticalCenter: parent.verticalCenter }
            spacing: Theme.px(6)

            Shape {
                visible: root.isDir
                width: Theme.px(9); height: width
                anchors.verticalCenter: parent.verticalCenter
                rotation: root.expanded ? 90 : 0
                Behavior on rotation { NumberAnimation { duration: Theme.fast } }
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: Theme.muted; strokeWidth: Theme.px(1.5); fillColor: "transparent"
                    capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                    startX: Theme.px(1); startY: 0
                    PathLine { x: Theme.px(7); y: Theme.px(4.5) }
                    PathLine { x: Theme.px(1); y: Theme.px(9) }
                }
            }
            Item { visible: !root.isDir; width: Theme.px(9); height: 1 }   // ruang kosong sejajar dengan panah folder

            Txt {
                text: root.name
                font.pixelSize: Theme.fsSmall
                color: root.isDir ? Theme.text : (row.active ? Theme.ink : Theme.muted)
                font.bold: root.isDir
            }
        }

        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.toggle()
        }
    }

    Column {
        id: kids
        width: root.width
        visible: root.isDir && root.expanded

        Repeater {
            model: root.isDir && root.expanded ? root.children : []
            delegate: Loader {
                id: childLoader
                required property var modelData
                width: kids.width
                source: Qt.resolvedUrl("FileTreeItem.qml")
                onLoaded: {
                    item.name = modelData.name
                    item.path = modelData.path
                    item.isDir = modelData.isDir
                    item.depth = root.depth + 1
                    item.activePath = Qt.binding(function () { return root.activePath })
                    item.openFile.connect(function (p) { root.openFile(p) })
                }
            }
        }
    }
}
