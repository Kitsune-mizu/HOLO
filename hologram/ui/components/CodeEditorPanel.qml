import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "../theme"

Rectangle {
    id: root
    radius: Theme.radius
    color: Theme.cardSolid
    border.color: Theme.line
    border.width: 1
    clip: true

    property string currentPath: ""
    property string savedText: ""
    property string appliedText: ""
    property bool logOpen: false
    property bool applying: false
    property bool applyInFlight: false

    // Tab file yang sedang terbuka di sesi ini (mirip tab bar VSCode).
    // Tiap entri: { path, content, savedText, appliedText }. Isi yang
    // belum disimpan tetap tersimpan di sini saat pindah tab, jadi tidak
    // hilang cuma karena klik file lain di Explorer.
    property var openBuffers: []
    property int activeBufferIndex: -1
    property bool closeConfirmVisible: false
    property int pendingCloseIndex: -1
    readonly property bool hasFile: currentPath !== ""
    readonly property bool dirty: hasFile && area.text !== savedText
    // Sudah disimpan ke disk tapi belum "Terapkan" (belum live) — dipakai
    // untuk highlight tombol Terapkan saja, bukan warna penanda.
    readonly property bool staged: hasFile && !dirty && savedText !== appliedText

    // Warna penanda file aktif, disatukan dengan skema penanda di
    // Explorer: "new" (hijau, file baru), "modified" (oranye, file lama
    // yang isinya berubah — termasuk saat masih diedit & belum disimpan),
    // "renamed" (abu-abu). Dipakai baik di titik header maupun garis tree.
    readonly property string currentMarkKind: {
        var kind = root.fileMarks[root.currentPath] || ""
        if (kind === "new") return "new"
        if (root.dirty) return "modified"
        return kind
    }

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

    function findBufferIndex(path) {
        for (var i = 0; i < root.openBuffers.length; i++) {
            if (root.openBuffers[i].path === path) return i
        }
        return -1
    }

    // Simpan isi editor yang lagi aktif ke dalam buffernya sebelum
    // pindah ke file lain, supaya perubahan yang belum di-Simpan tetap
    // ada begitu file itu dibuka lagi.
    function stashActiveBuffer() {
        if (root.activeBufferIndex < 0 || root.activeBufferIndex >= root.openBuffers.length) return
        var bufs = root.openBuffers.slice()
        var b = Object.assign({}, bufs[root.activeBufferIndex])
        b.content = area.text
        b.savedText = root.savedText
        b.appliedText = root.appliedText
        bufs[root.activeBufferIndex] = b
        root.openBuffers = bufs
    }

    // Dipanggil saat backend selesai membaca file dari disk (klik file
    // di Explorer). Kalau tabnya sudah ada, pakai isi buffer (yang
    // mungkin belum disimpan) — jangan ditimpa isi dari disk.
    function openAt(path, content) {
        root.stashActiveBuffer()

        var idx = root.findBufferIndex(path)
        if (idx === -1) {
            var buf = { path: path, content: content, savedText: content, appliedText: content }
            root.openBuffers = root.openBuffers.concat([buf])
            idx = root.openBuffers.length - 1
        }

        root.activeBufferIndex = idx
        var b = root.openBuffers[idx]
        root.currentPath = path
        root.savedText = b.savedText
        root.appliedText = b.appliedText
        area.text = b.content
        status.text = ""
    }

    // Pindah tab lokal saja, tanpa minta backend baca ulang dari disk.
    function switchToBuffer(idx) {
        if (idx < 0 || idx >= root.openBuffers.length || idx === root.activeBufferIndex) return
        root.stashActiveBuffer()
        root.activeBufferIndex = idx
        var b = root.openBuffers[idx]
        root.currentPath = b.path
        root.savedText = b.savedText
        root.appliedText = b.appliedText
        area.text = b.content
        status.text = ""
    }

    function isBufferDirty(idx) {
        var b = root.openBuffers[idx]
        if (!b) return false
        return idx === root.activeBufferIndex ? root.dirty : (b.content !== b.savedText)
    }

    function requestCloseBuffer(idx) {
        if (root.isBufferDirty(idx)) {
            root.pendingCloseIndex = idx
            root.closeConfirmVisible = true
        } else {
            root.closeBufferAt(idx)
        }
    }

    function closeBufferAt(idx) {
        if (idx < 0 || idx >= root.openBuffers.length) return
        var bufs = root.openBuffers.slice()
        var wasActive = (idx === root.activeBufferIndex)
        bufs.splice(idx, 1)
        root.openBuffers = bufs

        if (bufs.length === 0) {
            root.activeBufferIndex = -1
            root.currentPath = ""
            root.savedText = ""
            root.appliedText = ""
            area.text = ""
            status.text = ""
            return
        }

        if (wasActive) {
            var newIdx = Math.min(idx, bufs.length - 1)
            root.activeBufferIndex = -1
            root.switchToBuffer(newIdx)
        } else if (idx < root.activeBufferIndex) {
            root.activeBufferIndex -= 1
        }
    }

    function confirmCloseBuffer() {
        root.closeConfirmVisible = false
        var idx = root.pendingCloseIndex
        root.pendingCloseIndex = -1
        root.closeBufferAt(idx)
    }

    function cancelCloseBuffer() {
        root.closeConfirmVisible = false
        root.pendingCloseIndex = -1
    }

    function save() {
        if (!root.hasFile || root.applying) return
        root.applyInFlight = false
        editor.saveFile(root.currentPath, area.text)
    }

    function saveAndApply() {
        if (!root.hasFile || root.applying) return
        root.applyInFlight = true
        editor.applyFile(root.currentPath, area.text)
    }

    property string selectedPath: ""
    property bool selectedIsDir: false

    property bool isCreating: false
    property bool creatingIsDir: false
    property string createParentPath: ""
    property int refreshToken: 0

    // Penanda per file/folder di Explorer — bukan status editor,
    // tapi riwayat perubahan tiap item: "new" (baru dibuat/impor),
    // "modified" (file lama, isinya diedit), "renamed" (file lama
    // yang cuma diganti nama). Disimpan sebagai map path -> kind.
    property var fileMarks: ({})
    property string _pendingCreatePath: ""

    function markFile(path, kind) {
        try {
            if (!path) return
            var m = Object.assign({}, root.fileMarks)
            m[path] = kind
            root.fileMarks = m
        } catch (e) {
            root._log_ignore_error(e)
        }
    }

    function clearMarksUnder(path) {
        try {
            if (!path) return
            var m = Object.assign({}, root.fileMarks)
            var changed = false
            if (path in m) { delete m[path]; changed = true }
            for (var key in root.fileMarks) {
                if (key.indexOf(path + "/") === 0) { delete m[key]; changed = true }
            }
            if (changed) root.fileMarks = m
        } catch (e) {
            root._log_ignore_error(e)
        }
    }

    function migrateMarksOnRename(oldPath, newPath) {
        try {
            var old = root.fileMarks
            var m = {}
            for (var key in old) {
                if (key === oldPath || key.indexOf(oldPath + "/") === 0) continue
                m[key] = old[key]
            }
            var ownKind = old[oldPath]
            m[newPath] = (ownKind === "new") ? "new" : "renamed"
            for (key in old) {
                if (key.indexOf(oldPath + "/") === 0) {
                    m[newPath + key.slice(oldPath.length)] = old[key]
                }
            }
            root.fileMarks = m
        } catch (e) {
            root._log_ignore_error(e)
        }
    }

    // Fallback diam-diam kalau data penanda tidak terduga (mis. path
    // aneh dari backend) — jangan sampai error JS mematahkan UI Explorer.
    function _log_ignore_error(e) {
        if (typeof console !== "undefined") console.log("fileMarks:", e)
    }

    property bool deleteModalVisible: false
    property string pendingDeletePath: ""
    property string deleteModalWarning: ""
    property bool deleteIsProtected: false
    property bool deleteConfirmChecked: false

    property bool renameModalVisible: false
    property string pendingRenamePath: ""
    property string pendingRenameName: ""
    property string renameModalWarning: ""

    function requestDeleteConfirm(path) {
        pendingDeletePath = path
        deleteModalWarning = editor.getDeleteWarning(path)
        deleteIsProtected = editor.isProtectedFile(path)
        deleteConfirmChecked = false
        deleteModalVisible = true
    }

    function confirmDelete() {
        if (pendingDeletePath) {
            editor.logUiEvent("Delete dikonfirmasi: " + pendingDeletePath)
            editor.deleteFile(pendingDeletePath, root.deleteConfirmChecked)
        }
        deleteModalVisible = false
        pendingDeletePath = ""
        deleteConfirmChecked = false
    }

    function cancelDelete() {
        if (pendingDeletePath)
            editor.logUiEvent("Delete dibatalkan: " + pendingDeletePath)
        deleteModalVisible = false
        pendingDeletePath = ""
        deleteConfirmChecked = false
    }

    function requestRenameConfirm(path, newName) {
        var warning = editor.getRenameWarning(path, newName)

        if (!warning) {
            editor.renameFile(path, newName)
            return
        }

        if (warning.indexOf("dilindungi") >= 0) {
            root.pushToast(warning)
            return
        }

        pendingRenamePath = path
        pendingRenameName = newName
        renameModalWarning = warning
        renameModalVisible = true

        logModel.append({
            text: "[UI] Menunggu konfirmasi rename: " + path + " -> " + newName
        })
    }

    function confirmRename() {
        if (pendingRenamePath && pendingRenameName) {
            editor.renameFile(pendingRenamePath, pendingRenameName)
        }
        renameModalVisible = false
        pendingRenamePath = ""
        pendingRenameName = ""
        renameModalWarning = ""
    }

    function cancelRename() {
        renameModalVisible = false
        pendingRenamePath = ""
        pendingRenameName = ""
        renameModalWarning = ""
    }

    function selectedParentPath() {
        if (root.selectedIsDir) {
            return root.selectedPath
        }

        if (root.selectedPath) {
            var parts = root.selectedPath.split("/")
            parts.pop()
            return parts.join("/")
        }

        return ""
    }

    function triggerCreate(parentPath, isDir) {
        createParentPath = parentPath
        creatingIsDir = isDir
        isCreating = true
    }

    function cancelCreate() {
        isCreating = false
        createParentPath = ""
    }

    Connections {
        target: editor
        function onFileOpened(path, content) { root.openAt(path, content) }
        function onFileSaved(path) {
            root.savedText = area.text
            if (root.applyInFlight) {
                root.appliedText = area.text
                root.applyInFlight = false
            }
            // File lama yang isinya berubah -> oranye. Kalau path ini
            // baru saja dibuat, onFileSystemChanged di bawah akan
            // menimpanya jadi "new" setelahnya, jadi tetap aman.
            if (root.fileMarks[path] !== "new") root.markFile(path, "modified")
            status.text = "Tersimpan"
            statusTimer.restart()
        }
        function onFileSystemChanged() {
            root.pushToast("Explorer diperbarui.")
            // Hanya tandai "new" kalau ini memang hasil aksi buat/impor
            // yang baru saja diminta — bukan setiap sinyal fs berubah.
            if (root._pendingCreatePath) {
                root.markFile(root._pendingCreatePath, "new")
                root._pendingCreatePath = ""
            }
        }
        function onFileDeleted(path) {
            root.clearMarksUnder(path)
            // Tutup semua tab yang berada di dalam path yang dihapus
            // (file itu sendiri, atau isi folder yang dihapus).
            for (var i = root.openBuffers.length - 1; i >= 0; i--) {
                var p = root.openBuffers[i].path
                if (p === path || p.indexOf(path + "/") === 0) {
                    root.closeBufferAt(i)
                }
            }
            if (root.selectedPath === path || root.selectedPath.startsWith(path + "/")) {
                root.selectedPath = ""
                root.selectedIsDir = false
            }
        }
        function onFileRenamed(oldPath, newPath) {
            root.migrateMarksOnRename(oldPath, newPath)

            var bufs = root.openBuffers.slice()
            for (var i = 0; i < bufs.length; i++) {
                var p = bufs[i].path
                if (p === oldPath) {
                    bufs[i] = Object.assign({}, bufs[i], { path: newPath })
                } else if (p.indexOf(oldPath + "/") === 0) {
                    bufs[i] = Object.assign({}, bufs[i], { path: newPath + p.slice(oldPath.length) })
                }
            }
            root.openBuffers = bufs

            if (root.currentPath === oldPath) {
                root.currentPath = newPath
            } else if (root.currentPath.startsWith(oldPath + "/")) {
                root.currentPath = newPath + root.currentPath.slice(oldPath.length)
            }
            if (root.selectedPath === oldPath)
                root.selectedPath = newPath
            root.pushToast("Rename berhasil: " + oldPath + " -> " + newPath)
        }
        function onErrorOccurred(message) {
            root.pushToast(message)
        }
        function onReloading(active) { root.applying = active }
        function onLogMessage(line) {
            logModel.append({ text: line })
            if (logModel.count > 200) logModel.remove(0)
            Qt.callLater(function () { logList.positionViewAtEnd() })
        }
    }
    Timer { id: statusTimer; interval: 3200; onTriggered: status.text = "" }
    ListModel { id: logModel }

    Shortcut { sequence: "Ctrl+S"; onActivated: root.save() }
    Shortcut { sequence: "Ctrl+Shift+S"; onActivated: root.saveAndApply() }

    // Header
    Item {
        id: head
        height: Theme.px(40)
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: Theme.px(10) }

        Txt {
            anchors { 
                left: parent.left
                leftMargin: Theme.px(10) 
                verticalCenter: parent.verticalCenter 
            }
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
                visible: root.currentMarkKind !== ""
                width: Theme.px(7); height: width; radius: width / 2
                color:
                    root.currentMarkKind === "new" ? "#5cb85c"
                    : root.currentMarkKind === "modified" ? "#e0a13c"
                    : root.currentMarkKind === "renamed" ? "#9aa0a8"
                    : "transparent"
                anchors.verticalCenter: parent.verticalCenter

                Behavior on color { ColorAnimation { duration: 150 } }
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
                text: "Terapkan"
                checked: root.dirty || root.staged
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

        // Kiri: Explorer
        Rectangle {
            width: Math.min(Theme.px(240), body.width * 0.32)
            height: parent.height
            radius: Theme.radiusSmall
            color: Theme.tint
            border.color: Theme.line
            border.width: 1

            Item {
                id: explorerHeader
                anchors { top: parent.top; left: parent.left; right: parent.right }
                height: Theme.px(30)

                Txt {
                    anchors { left: parent.left; leftMargin: Theme.px(8); verticalCenter: parent.verticalCenter }
                    text: "BERKAS"
                    font.bold: true
                    font.pixelSize: Theme.fsSmall * 0.9
                    color: Theme.dim
                }

                Row {
                    anchors {
                        right: parent.right
                        rightMargin: Theme.px(6)
                        verticalCenter: parent.verticalCenter
                    }

                    spacing: Theme.px(4)

                    // + Button
                    Rectangle {
                        id: addButton

                        width: Theme.px(24)
                        height: Theme.px(24)

                        radius: Theme.px(4)

                        color:
                            addButtonArea.containsMouse
                                ? Theme.tintStrong
                                : "transparent"

                        border.color:
                            addButtonArea.containsMouse
                                ? Theme.line
                                : "transparent"

                        border.width: 1

                        Text {
                            anchors.centerIn: parent

                            text: "+"

                            color: Theme.ink

                            font.pixelSize:
                                Theme.fsBody

                            font.bold: true
                        }

                        MouseArea {
                            id: addButtonArea

                            anchors.fill: parent

                            hoverEnabled: true

                            cursorShape:
                                Qt.PointingHandCursor

                            onClicked:
                                addMenu.popup()
                        }

                        ToolTip.visible:
                            addButtonArea.containsMouse

                        ToolTip.text:
                            "Tambah"

                        ToolTip.delay: 500
                    }

                    Menu {
                        id: addMenu

                        topPadding: Theme.px(4)
                        bottomPadding: Theme.px(4)
                        leftPadding: Theme.px(4)
                        rightPadding: Theme.px(4)

                        background: Rectangle {
                            implicitWidth: Theme.px(150)
                            color: Theme.cardSolid
                            border.color: Theme.line
                            border.width: 1
                            radius: Theme.radiusSmall
                        }

                        MenuItem {
                            id: miNewFile
                            text: "File Baru"
                            height: Theme.px(28)

                            contentItem: Txt {
                                text: miNewFile.text
                                font.pixelSize: Theme.fsSmall
                                color: Theme.text
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.px(8)
                            }

                            background: Rectangle {
                                radius: Theme.px(4)
                                color: miNewFile.hovered ? Theme.tintStrong : "transparent"
                            }

                            onTriggered: {
                                root.triggerCreate(root.selectedParentPath(), false)
                            }
                        }

                        MenuItem {
                            id: miNewFolder
                            text: "Folder Baru"
                            height: Theme.px(28)

                            contentItem: Txt {
                                text: miNewFolder.text
                                font.pixelSize: Theme.fsSmall
                                color: Theme.text
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.px(8)
                            }

                            background: Rectangle {
                                radius: Theme.px(4)
                                color: miNewFolder.hovered ? Theme.tintStrong : "transparent"
                            }

                            onTriggered: {
                                root.triggerCreate(root.selectedParentPath(), true)
                            }
                        }
                    }

                    // Refresh Button
                    Rectangle {
                        id: refreshButton
                        width: Theme.px(24)
                        height: Theme.px(24)
                        radius: Theme.px(4)
                        color: refreshArea.containsMouse ? Theme.tintStrong : "transparent"
                        border.color: refreshArea.containsMouse ? Theme.line : "transparent"
                        border.width: 1

                        // Tanpa animasi putar — sebelumnya selalu tampak lonjong
                        // walau dibungkus item persegi, jadi dihilangkan saja.
                        Text {
                            id: refreshIcon
                            anchors.centerIn: parent
                            text: "⟳"
                            color: Theme.ink
                            font.pixelSize: Theme.fsBody
                        }

                        MouseArea {
                            id: refreshArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.refreshToken += 1
                                root.pushToast("Explorer disegarkan.")
                            }
                        }

                        ToolTip.visible: refreshArea.containsMouse
                        ToolTip.text: "Segarkan Explorer"
                        ToolTip.delay: 500
                    }

                    // Impor Button
                    Rectangle {
                        width: Theme.px(46)
                        height: Theme.px(24)

                        radius: Theme.px(4)

                        color:
                            importArea.containsMouse
                                ? Theme.tintStrong
                                : "transparent"

                        Text {
                            anchors.centerIn: parent

                            text: "Impor"

                            color: Theme.muted

                            font.pixelSize:
                                Theme.fsSmall * 0.9
                        }

                        MouseArea {
                            id: importArea

                            anchors.fill: parent

                            hoverEnabled: true

                            cursorShape:
                                Qt.PointingHandCursor

                            onClicked: fileDialog.open()
                        }

                        ToolTip.visible:
                            importArea.containsMouse

                        ToolTip.text:
                            "Impor file eksternal"

                        ToolTip.delay: 500
                    }
                }

                Rectangle {
                    anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
                    height: 1
                    color: Theme.line
                }
            }

            ScrollView {
                id: fileScroll
                anchors { top: explorerHeader.bottom; left: parent.left; right: parent.right; bottom: parent.bottom }
                anchors.margins: Theme.px(4)
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                Column {
                    width: fileScroll.availableWidth
                    spacing: Theme.px(2)

                    FileTreeItem {
                        id: tree
                        width: parent.width
                        name: editor.rootName
                        path: ""
                        isDir: true
                        depth: 0
                        activePath: root.currentPath
                        selectedPath: root.selectedPath
                        fileMarks: root.fileMarks
                        activeDirty: root.dirty
                        creatingActive: root.isCreating
                        creatingPath: root.createParentPath
                        creatingIsDir: root.creatingIsDir
                        refreshToken: root.refreshToken
                        onOpenFile: (p) => editor.openFile(p)
                        onBeginCreate: (p) => root._pendingCreatePath = p
                        onSelectItem: (p, d) => {
                            root.selectedPath = p
                            root.selectedIsDir = d
                        }
                        onRequestDelete: (p) => root.requestDeleteConfirm(p)
                        onRequestCreate: (parentP, d) => root.triggerCreate(parentP, d)
                        onRequestRename: (p, n) => root.requestRenameConfirm(p, n)
                        onCreateFinished: root.cancelCreate()
                        Component.onCompleted: { expanded = true; children = editor.listDir("") }
                    }
                }
            }

            FileDialog {
                id: fileDialog
                title: "Pilih file untuk diimpor ke proyek"
                onAccepted: {
                    var dest = root.selectedParentPath()
                    if (dest) {
                        dest += "/"
                    }
                    var srcParts = fileDialog.selectedFile.toString().split("/")
                    var srcName = decodeURIComponent(srcParts[srcParts.length - 1] || "")
                    root._pendingCreatePath = dest ? (dest + srcName) : srcName
                    editor.importFile(fileDialog.selectedFile.toString(), dest)
                }
            }
        }

        // Kanan: Editor Teks
        Rectangle {
            width: parent.width - Math.min(Theme.px(240), body.width * 0.32) - Theme.px(10)
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

            // Bar tab file yang sedang dibuka, mirip tab editor VSCode.
            // Pindah tab tidak membuang perubahan yang belum disimpan.
            Rectangle {
                id: tabBar
                visible: root.openBuffers.length > 0
                anchors { top: parent.top; left: parent.left; right: parent.right; margins: 1 }
                height: visible ? Theme.px(30) : 0
                radius: Theme.radiusSmall
                color: Theme.cardSolid
                clip: true

                ScrollView {
                    anchors.fill: parent
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                    ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                    contentWidth: tabRow.implicitWidth
                    contentHeight: tabBar.height

                    Row {
                        id: tabRow
                        height: tabBar.height
                        spacing: Theme.px(2)

                        Repeater {
                            model: root.openBuffers

                            delegate: Rectangle {
                                id: tabDelegate
                                required property var modelData
                                required property int index

                                readonly property bool isActive: index === root.activeBufferIndex
                                readonly property bool tabDirty:
                                    isActive
                                        ? root.dirty
                                        : (modelData.content !== modelData.savedText)
                                readonly property string baseName: {
                                    var parts = modelData.path.split("/")
                                    return parts[parts.length - 1] || modelData.path
                                }

                                width: Theme.px(150)
                                height: tabBar.height
                                color: isActive ? Theme.tint : "transparent"

                                Rectangle {
                                    visible: tabDelegate.isActive
                                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                                    height: Theme.px(2)
                                    color: Theme.ink
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.switchToBuffer(tabDelegate.index)
                                }

                                Row {
                                    anchors {
                                        left: parent.left; right: parent.right
                                        verticalCenter: parent.verticalCenter
                                        leftMargin: Theme.px(10); rightMargin: Theme.px(6)
                                    }
                                    spacing: Theme.px(6)

                                    Rectangle {
                                        visible: tabDelegate.tabDirty
                                        width: Theme.px(6); height: width; radius: width / 2
                                        color: "#e0a13c"
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Txt {
                                        width: parent.width - Theme.px(28) - (tabDelegate.tabDirty ? Theme.px(12) : 0)
                                        text: tabDelegate.baseName
                                        elide: Text.ElideRight
                                        font.pixelSize: Theme.fsSmall * 0.9
                                        color: tabDelegate.isActive ? Theme.ink : Theme.muted
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        text: "×"
                                        font.pixelSize: Theme.fsSmall
                                        font.bold: true
                                        color: closeArea.containsMouse ? Theme.warn : Theme.dim
                                        anchors.verticalCenter: parent.verticalCenter

                                        MouseArea {
                                            id: closeArea
                                            anchors.fill: parent
                                            anchors.margins: -Theme.px(5)
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.requestCloseBuffer(tabDelegate.index)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            ScrollView {
                visible: root.hasFile
                anchors {
                    top: tabBar.visible ? tabBar.bottom : parent.top
                    left: parent.left; right: parent.right; bottom: parent.bottom
                    topMargin: tabBar.visible ? Theme.px(6) : Theme.px(10)
                    leftMargin: Theme.px(10); rightMargin: Theme.px(10); bottomMargin: Theme.px(10)
                }
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
                    leftPadding: Theme.px(50)

                    Component.onCompleted: {
                        if (typeof editor !== "undefined" && editor.setupHighlighter)
                            editor.setupHighlighter(area.textDocument)
                    }

                    Item {
                        x: 0; y: 0
                        width: Theme.px(40)
                        height: parent.height

                        Rectangle {
                            anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
                            width: 1
                            color: Theme.line
                        }
                        Text {
                            anchors { right: parent.right; rightMargin: Theme.px(8) }
                            y: area.topPadding
                            text: {
                                var s = ""; var n = area.lineCount || 1
                                for (var i = 1; i <= n; i++) s += i + (i === n ? "" : "\n")
                                return s
                            }
                            font: area.font
                            color: Theme.dim
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }
            }
        }
    }

    // Panel Log
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

    // Toast
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

        Rectangle {
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
            text: "✕"
            color: Theme.dim
            font.pixelSize: Theme.fsSmall
            anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: Theme.px(12) }

            MouseArea {
                anchors.fill: parent
                anchors.margins: -Theme.px(8)
                cursorShape: Qt.PointingHandCursor
                onClicked: root.showNextToast()
            }
        }
    }
    Timer { id: toastTimer; interval: 4500; onTriggered: root.showNextToast() }

    // Reloading Overlay
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

    // Modal tutup tab yang belum disimpan — mirip VSCode: OK (tutup,
    // buang perubahan) atau Cancel (batal, tab tetap terbuka).
    Rectangle {
        id: closeConfirmModal
        anchors.fill: parent
        visible: root.closeConfirmVisible
        color: Qt.rgba(0, 0, 0, 0.6)
        z: 52

        MouseArea { anchors.fill: parent; onClicked: {} }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width - Theme.px(40), Theme.px(420))
            implicitHeight: closeConfirmCol.implicitHeight + Theme.px(32)
            radius: Theme.radius
            color: Theme.cardSolid
            border.color: Theme.line
            border.width: 1

            Column {
                id: closeConfirmCol
                anchors { top: parent.top; left: parent.left; right: parent.right; margins: Theme.px(16) }
                spacing: Theme.px(14)

                Txt {
                    text: "File Belum Disimpan"
                    font.bold: true
                    font.pixelSize: Theme.fsBody
                    color: Theme.ink
                }

                Txt {
                    width: parent.width
                    text: "Perubahan pada file ini belum disimpan. Tutup tab dan buang perubahannya?"
                    wrapMode: Text.Wrap
                    font.pixelSize: Theme.fsSmall
                    color: Theme.text
                }

                Row {
                    anchors.right: parent.right
                    spacing: Theme.px(10)

                    Rectangle {
                        width: Theme.px(76); height: Theme.px(28)
                        radius: Theme.px(4)
                        color: closeCancelArea.containsMouse ? Theme.tintStrong : Theme.tint
                        border.color: Theme.line
                        border.width: 1

                        Txt {
                            anchors.centerIn: parent
                            text: "Cancel"
                            font.pixelSize: Theme.fsSmall
                            color: Theme.text
                        }

                        MouseArea {
                            id: closeCancelArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: root.cancelCloseBuffer()
                        }
                    }

                    Rectangle {
                        width: Theme.px(76); height: Theme.px(28)
                        radius: Theme.px(4)
                        color: closeOkArea.containsMouse ? Theme.warn : Theme.tintStrong
                        border.color: Theme.line
                        border.width: 1

                        Txt {
                            anchors.centerIn: parent
                            text: "OK"
                            font.pixelSize: Theme.fsSmall
                            font.bold: true
                            color: Theme.text
                        }

                        MouseArea {
                            id: closeOkArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: root.confirmCloseBuffer()
                        }
                    }
                }
            }
        }
    }

    // Modal Rename
    Rectangle {
        id: renameModal

        anchors.fill: parent

        visible: root.renameModalVisible

        color: Qt.rgba(0, 0, 0, 0.6)

        z: 51

        MouseArea {
            anchors.fill: parent
            onClicked: {}
        }

        Rectangle {
            anchors.centerIn: parent

            width: Math.min(
                parent.width - Theme.px(40),
                Theme.px(440)
            )

            implicitHeight:
                renameColumn.implicitHeight + Theme.px(32)

            radius: Theme.radius
            color: Theme.cardSolid
            border.color: Theme.line
            border.width: 1

            Column {
                id: renameColumn

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                    margins: Theme.px(16)
                }

                spacing: Theme.px(14)

                Txt {
                    text: "Konfirmasi Rename"
                    font.bold: true
                    font.pixelSize: Theme.fsBody
                    color: Theme.ink
                }

                Txt {
                    width: parent.width
                    text: root.renameModalWarning
                    wrapMode: Text.Wrap
                    font.pixelSize: Theme.fsSmall
                    color: Theme.text
                }

                Txt {
                    width: parent.width
                    text: "Nama baru: " + root.pendingRenameName
                    font.pixelSize: Theme.fsSmall
                    color: Theme.muted
                }

                Row {
                    anchors.right: parent.right
                    spacing: Theme.px(10)

                    Rectangle {
                        width: Theme.px(76)
                        height: Theme.px(28)
                        radius: Theme.px(4)
                        color: renameCancelArea.containsMouse ? Theme.tintStrong : Theme.tint
                        border.color: Theme.line
                        border.width: 1

                        Txt {
                            anchors.centerIn: parent
                            text: "Cancel"
                            font.pixelSize: Theme.fsSmall
                            color: Theme.text
                        }

                        MouseArea {
                            id: renameCancelArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: root.cancelRename()
                        }
                    }

                    Rectangle {
                        width: Theme.px(76)
                        height: Theme.px(28)
                        radius: Theme.px(4)
                        color: renameOkArea.containsMouse ? Theme.ink : Theme.tintStrong
                        border.color: Theme.line
                        border.width: 1

                        Txt {
                            anchors.centerIn: parent
                            text: "OK"
                            font.pixelSize: Theme.fsSmall
                            font.bold: true
                            color: Theme.text
                        }

                        MouseArea {
                            id: renameOkArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: root.confirmRename()
                        }
                    }
                }
            }
        }
    }

    // Modal Delete
    Rectangle {
        id: deleteModal
        anchors.fill: parent
        visible: root.deleteModalVisible
        color: Qt.rgba(0, 0, 0, 0.6)
        z: 50

        MouseArea {
            anchors.fill: parent
            onClicked: {}
        }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width - Theme.px(40), Theme.px(420))
            implicitHeight: modalCol.implicitHeight + Theme.px(32)
            radius: Theme.radius
            color: Theme.cardSolid
            border.color: Theme.line
            border.width: 1

            Column {
                id: modalCol
                anchors { top: parent.top; left: parent.left; right: parent.right; margins: Theme.px(16) }
                spacing: Theme.px(14)

                Txt {
                    text: "Konfirmasi Penghapusan"
                    font.bold: true
                    font.pixelSize: Theme.fsBody
                    color: Theme.ink
                }

                Txt {
                    width: parent.width
                    text: root.deleteModalWarning
                    wrapMode: Text.Wrap
                    font.pixelSize: Theme.fsSmall
                    color: Theme.text
                }

                // Checkbox konfirmasi khusus file inti/protected — hanya
                // muncul kalau file yang dihapus terdeteksi penting.
                Rectangle {
                    visible: root.deleteIsProtected
                    width: parent.width
                    height: confirmRow.implicitHeight + Theme.px(16)
                    radius: Theme.radiusSmall
                    color: Qt.rgba(Theme.warn.r, Theme.warn.g, Theme.warn.b, 0.1)
                    border.color: Theme.warn
                    border.width: 1

                    Row {
                        id: confirmRow
                        anchors { fill: parent; margins: Theme.px(10) }
                        spacing: Theme.px(10)

                        Rectangle {
                            id: confirmBox
                            width: Theme.px(18); height: Theme.px(18)
                            radius: Theme.px(4)
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.deleteConfirmChecked ? Theme.warn : "transparent"
                            border.color: Theme.warn
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                visible: root.deleteConfirmChecked
                                text: "✓"
                                color: "#ffffff"
                                font.pixelSize: Theme.fsSmall
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -Theme.px(4)
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.deleteConfirmChecked = !root.deleteConfirmChecked
                            }
                        }

                        Txt {
                            width: parent.width - confirmBox.width - parent.spacing
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Saya memahami risikonya dan tetap ingin menghapus file ini."
                            wrapMode: Text.Wrap
                            font.pixelSize: Theme.fsSmall * 0.92
                            color: Theme.text
                        }
                    }
                }

                Item { width: 1; height: Theme.px(2) }

                Row {
                    anchors.right: parent.right
                    spacing: Theme.px(10)

                    Rectangle {
                        width: Theme.px(76); height: Theme.px(28)
                        radius: Theme.px(4)
                        color: cancelHover.containsMouse ? Theme.tintStrong : Theme.tint
                        border.color: Theme.line; border.width: 1
                        Txt {
                            anchors.centerIn: parent
                            text: "Batal"
                            font.pixelSize: Theme.fsSmall
                            color: Theme.text
                        }
                        MouseArea {
                            id: cancelHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.cancelDelete()
                        }
                    }

                    Rectangle {
                        readonly property bool allowed: !root.deleteIsProtected || root.deleteConfirmChecked
                        width: Theme.px(76); height: Theme.px(28)
                        radius: Theme.px(4)
                        opacity: allowed ? 1 : 0.45
                        color: (allowed && okHover.containsMouse) ? Qt.darker(Theme.warn, 1.2) : Theme.warn
                        Txt {
                            anchors.centerIn: parent
                            text: "Hapus"
                            font.pixelSize: Theme.fsSmall
                            font.bold: true
                            color: "#ffffff"
                        }
                        MouseArea {
                            id: okHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: parent.allowed ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                            onClicked: {
                                if (parent.allowed) root.confirmDelete()
                            }
                        }
                    }
                }
            }
        }
    }
}