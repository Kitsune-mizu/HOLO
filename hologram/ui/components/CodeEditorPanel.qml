import QtQuick
import QtQuick.Controls
import "../theme"

// Editor kode sederhana di dalam aplikasi: pohon folder proyek di kiri, isi file di kanan.
// Bukan IDE penuh -- tanpa penyorotan sintaks, tanpa tab banyak file -- cukup untuk melihat dan
// mengubah satu file, lalu menyimpannya (dan kalau mau, langsung menerapkannya juga).
//
// Dua tombol simpan:
// - "Simpan": hanya menulis ke disk.
// - "Simpan & Terapkan": menulis ke disk LALU langsung berlaku pada aplikasi yang sedang jalan --
//   file .qml dimuat ulang di tempat (cepat, tanpa menutup aplikasi), file lain (Python, config)
//   membuat aplikasi memulai ulang dirinya sendiri secara otomatis (lihat hologram/core/editor.py).
Rectangle {
    id: root
    radius: Theme.radius
    color: Theme.cardSolid
    border.color: Theme.line
    border.width: 1
    clip: true

    property string currentPath: ""
    property string savedText: ""
    property bool logOpen: false
    property bool applying: false      // true selagi menunggu reload QML / restart aplikasi
    readonly property bool hasFile: currentPath !== ""
    readonly property bool dirty: hasFile && area.text !== savedText

    // Toast: notifikasi mengambang untuk error/peringatan, supaya tidak cuma lewat sekilas di
    // teks status kecil atau tertimbun di panel log. Kalau beberapa muncul cepat berurutan,
    // ditampilkan satu-satu bergantian (antrean), bukan saling menimpa.
    property var toastQueue: []
    property string toastText: ""
    property bool toastVisible: false

    function pushToast(message) {
        toastQueue.push(message)
        if (!toastVisible) showNextToast()
    }
    function showNextToast() {
        toastTimer.stop()
        if (toastQueue.length === 0) { toastVisible = false; return }
        toastText = toastQueue.shift()
        toastVisible = true
        toastTimer.restart()
    }

    function openAt(path, content) {
        root.currentPath = path
        root.savedText = content
        area.text = content
        status.text = ""
    }

    function save() {
        if (!root.hasFile || root.applying) return
        editor.saveFile(root.currentPath, area.text)
    }

    function saveAndApply() {
        if (!root.hasFile || root.applying) return
        editor.applyFile(root.currentPath, area.text)
    }

    Connections {
        target: editor
        function onFileOpened(path, content) { root.openAt(path, content) }
        function onFileSaved(path) { root.savedText = area.text; status.text = "Tersimpan"; statusTimer.restart() }
        function onErrorOccurred(message) { status.text = message; statusTimer.restart(); root.pushToast(message) }
        function onReloading(active) { root.applying = active }
        function onLogMessage(line) {
            logModel.append({ text: line })
            if (logModel.count > 200) logModel.remove(0)     // jangan tumbuh tanpa batas selama aplikasi hidup
            Qt.callLater(function () { logList.positionViewAtEnd() })
        }
    }
    Timer { id: statusTimer; interval: 3200; onTriggered: status.text = "" }
    ListModel { id: logModel }

    Shortcut { sequence: "Ctrl+S"; onActivated: root.save() }
    Shortcut { sequence: "Ctrl+Shift+S"; onActivated: root.saveAndApply() }

    // Header: judul, path file aktif + titik "belum tersimpan", tombol log, tombol simpan.
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
            spacing: Theme.px(8)
            Txt { id: status; text: ""; font.pixelSize: Theme.fsSmall; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
            ToggleButton {
                text: "Log"
                showChevron: true
                checked: root.logOpen
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.logOpen = !root.logOpen
            }
            ToggleButton {
                text: "Simpan"
                checked: root.dirty
                enabled: root.hasFile && !root.applying
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.save()
            }
            ToggleButton {
                text: "Simpan & Terapkan"
                checked: true
                enabled: root.hasFile && !root.applying
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.saveAndApply()
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
        id: body
        anchors { top: divider.bottom; topMargin: Theme.px(8); left: parent.left; right: parent.right; margins: Theme.px(10) }
        height: parent.height - y - (root.logOpen ? logPanel.height + Theme.px(8) : 0) - Theme.px(10)
        Behavior on height { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        spacing: Theme.px(10)
        clip: true

        // Kiri: pohon file
        Rectangle {
            width: Math.min(Theme.px(260), body.width * 0.32)
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
                    readOnly: root.applying
                }
            }
        }
    }

    // Panel log: baris demi baris, disembunyikan secara default. Auto-scroll ke bawah tiap baris baru.
    Rectangle {
        id: logPanel
        visible: root.logOpen
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: Theme.px(10) }
        height: root.logOpen ? Theme.px(120) : 0
        radius: Theme.radiusSmall
        color: Theme.tint
        border.color: Theme.line
        border.width: 1

        ListView {
            id: logList
            anchors.fill: parent
            anchors.margins: Theme.px(8)
            clip: true
            model: logModel
            boundsBehavior: Flickable.StopAtBounds
            delegate: Txt {
                width: logList.width
                text: model.text
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fsSmall * 0.92
                color: Theme.muted
            }
        }
        Txt {
            visible: logModel.count === 0
            anchors.centerIn: parent
            text: "Belum ada aktivitas."
            color: Theme.dim
            font.pixelSize: Theme.fsSmall
        }
    }

    // Toast error/peringatan: mengambang di atas isi panel, warna aksen kuning peringatan.
    Rectangle {
        id: toast
        opacity: root.toastVisible ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: Theme.px(46) }
        width: Math.min(parent.width - Theme.px(48), Theme.px(560))
        height: Math.max(Theme.px(40), toastMsg.implicitHeight + Theme.px(20))
        radius: Theme.radiusSmall
        color: Theme.cardSolid
        border.color: Theme.line
        border.width: 1
        z: 40

        Rectangle {                              // batang aksen kiri, penanda ini peringatan/error
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 1 }
            width: Theme.px(3)
            radius: Theme.px(1.5)
            color: Theme.warn
        }
        Txt {
            id: toastMsg
            anchors { left: parent.left; right: toastClose.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.px(16); rightMargin: Theme.px(6) }
            text: root.toastText
            wrapMode: Text.Wrap
            color: Theme.text
            font.pixelSize: Theme.fsSmall
        }
        Text {
            id: toastClose
            anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: Theme.px(12) }
            text: "\u2715"
            color: Theme.dim
            font.pixelSize: Theme.fsSmall
            MouseArea {
                anchors.fill: parent
                anchors.margins: -Theme.px(8)
                cursorShape: Qt.PointingHandCursor
                onClicked: root.showNextToast()
            }
        }
    }
    Timer { id: toastTimer; interval: 4500; onTriggered: root.showNextToast() }

    // Overlay "menerapkan...": tampil sesaat sebelum QML dimuat ulang, atau lebih lama sebelum
    // aplikasi me-restart dirinya sendiri. Titik yang berputar supaya terasa hidup, bukan macet.
    Rectangle {
        anchors.fill: parent
        visible: root.applying
        color: Qt.rgba(0.075, 0.07, 0.06, 0.92)
        radius: Theme.radius

        Column {
            anchors.centerIn: parent
            spacing: Theme.px(14)

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Theme.px(8)
                Repeater {
                    model: 3
                    Rectangle {
                        width: Theme.px(9); height: width; radius: width / 2
                        color: Theme.ink
                        property real phase: index * 0.25
                        opacity: 0.35 + 0.65 * Math.abs(Math.sin((pulseTimer.t + phase) * Math.PI))
                    }
                }
            }
            Txt {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.currentPath.endsWith(".qml") ? "Memuat ulang tampilan..." : "Memulai ulang aplikasi..."
                color: Theme.text
                font.pixelSize: Theme.fsBody
            }
        }
        Timer {
            id: pulseTimer
            property real t: 0
            interval: 33; running: root.applying; repeat: true
            onTriggered: t += 0.06
        }
    }
}
