import QtQuick
import QtQuick.Controls
import "../theme"

Column {
    id: root

    property string name: ""
    property string path: ""
    property bool isDir: false
    property int depth: 0

    property string activePath: ""
    property string selectedPath: ""

    // Riwayat perubahan tiap file/folder di seluruh tree, bukan cuma
    // yang lagi aktif di editor: path -> "new" | "modified" | "renamed".
    // Diteruskan turun apa adanya (object yang sama) ke semua anak.
    property var fileMarks: ({})

    // Status "sedang diedit, belum disimpan" utk file yang lagi aktif —
    // dipakai supaya baris file lama yang lagi diketik langsung tampak
    // oranye di pinggirnya juga, tidak menunggu sampai disimpan dulu.
    property bool activeDirty: false

    property bool expanded: false
    property var children: []

    // Status pembuatan file/folder baru, diteruskan turun secara rekursif
    // dari CodeEditorPanel supaya input "buat baru" muncul persis di lokasi
    // yang sedang dipilih (folder yang diklik), bukan selalu di atas.
    property bool creatingActive: false
    property string creatingPath: ""
    property bool creatingIsDir: false

    // Token yang dinaikkan manual lewat tombol refresh di header Explorer;
    // setiap kali berubah, folder yang sedang terbuka memuat ulang isinya.
    property int refreshToken: 0
    onRefreshTokenChanged: {
        if (root.isDir && root.expanded) {
            root.children = editor.listDir(root.path)
        }
    }

    readonly property bool showCreateHere:
        root.isDir && root.expanded && root.creatingActive && root.path === root.creatingPath

    signal openFile(string path)
    signal selectItem(string path, bool isDir)
    signal requestDelete(string path)
    signal requestCreate(string parentPath, bool isDir)
    signal requestRename(string path, string newName)
    signal createFinished()
    // Dipancarkan tepat sebelum memanggil editor.createFile/createFolder,
    // supaya panel tahu path mana yang harus ditandai "new" begitu
    // backend konfirmasi lewat fileSystemChanged.
    signal beginCreate(string path)

    width: parent ? parent.width : 0

    // -----------------------------------------------------------
    // Ikon: badge kecil bergaya, konsisten ukurannya untuk semua
    // baris (folder maupun file), supaya rapi & seragam.
    // -----------------------------------------------------------
    function extBadge(n) {
        n = (n || "").toLowerCase()
        var dot = n.lastIndexOf(".")

        // Tidak ada titik sama sekali (mis. "Makefile", "Dockerfile")
        if (dot < 0) return "•"

        // Dotfile murni (".env", ".gitignore", ".npmrc", dst) — titiknya
        // ada di index 0, bukan pemisah ekstensi. Sebelumnya ini ikut
        // masuk kondisi "tidak ada ekstensi" dan cuma dapat badge "•".
        if (dot === 0) {
            var dotMap = {
                "env": "ENV", "gitignore": "GIT", "gitattributes": "GIT",
                "dockerignore": "DKR", "editorconfig": "CFG",
                "npmrc": "NPM", "eslintrc": "ESL", "prettierrc": "PRT",
                "babelrc": "BBL", "nvmrc": "NVM"
            }
            var full = n.slice(1)
            return dotMap[full] || full.slice(0, 3).toUpperCase() || "•"
        }

        var map = {
            "py": "PY", "qml": "QML", "json": "JSN", "toml": "TML",
            "md": "MD", "txt": "TXT", "js": "JS", "ts": "TS",
            "html": "HTM", "css": "CSS", "yml": "YML", "yaml": "YML",
            "sh": "SH", "png": "IMG", "jpg": "IMG", "jpeg": "IMG",
            "svg": "SVG", "ico": "ICO"
        }
        var ext = n.slice(dot + 1)
        return map[ext] || ext.slice(0, 3).toUpperCase()
    }

    function extColor(n) {
        n = (n || "").toLowerCase()
        if (n.startsWith(".env")) return "#e0a13c"
        if (n === ".gitignore" || n === ".gitattributes" || n === ".dockerignore") return "#8a8f98"
        if (n.endsWith(".py")) return "#4b8bbe"
        if (n.endsWith(".qml")) return "#8a63d2"
        if (n.endsWith(".json")) return "#c9a227"
        if (n.endsWith(".toml") || n.endsWith(".ini") || n.endsWith(".cfg")) return "#5c9e6f"
        if (n.endsWith(".js") || n.endsWith(".ts")) return "#d2b34c"
        if (n.endsWith(".html")) return "#d2694c"
        if (n.endsWith(".css")) return "#4c9ed2"
        return Theme.muted
    }

    function toggle() {
        root.selectItem(root.path, root.isDir)

        if (!root.isDir) {
            root.openFile(root.path)
            return
        }

        root.expanded = !root.expanded

        if (root.expanded && root.children.length === 0) {
            root.children = editor.listDir(root.path)
        }
    }

    // Auto-refresh: setiap node folder yang sedang terbuka akan
    // memuat ulang isinya sendiri saat ada perubahan filesystem,
    // sehingga tambah/hapus/rename langsung terlihat di semua level.
    Connections {
        target: editor
        function onFileSystemChanged() {
            if (root.isDir && root.expanded) {
                root.children = editor.listDir(root.path)
            }
        }
    }

    Rectangle {
        id: row

        width: root.width
        height: Theme.px(24)
        radius: Theme.px(5)

        readonly property bool isSelected:
            root.path === root.selectedPath

        readonly property bool active:
            !root.isDir && root.path === root.activePath

        color:
            row.isSelected
                ? Theme.tintStrong
                : (area.containsMouse
                    ? Theme.tint
                    : (row.active ? Theme.tint : "transparent"))

        property bool isEditing: false

        // "" kalau tidak ada penanda. Fallback aman kalau fileMarks
        // belum ter-set / bukan object yang diharapkan. File baru yang
        // sedang diedit tetap hijau; file lama yang sedang diedit (belum
        // disimpan) langsung tampil oranye tanpa menunggu Simpan.
        readonly property string markKind: {
            try {
                var raw = (root.fileMarks && root.fileMarks[root.path]) || ""
                if (raw === "new") return "new"
                if (row.active && root.activeDirty) return "modified"
                return raw
            } catch (e) {
                return ""
            }
        }

        readonly property color markColor:
            row.markKind === "new" ? "#5cb85c"
            : row.markKind === "modified" ? "#e0a13c"
            : row.markKind === "renamed" ? "#9aa0a8"
            : "transparent"

        // Garis status di pinggir kiri baris, mirip decorator git di VSCode:
        // hijau = file/folder baru, oranye = file lama yang diedit isinya,
        // abu-abu = file lama yang cuma diganti nama.
        Rectangle {
            visible: row.markKind !== ""
            anchors {
                left: parent.left
                top: parent.top
                bottom: parent.bottom
            }
            width: Theme.px(3)
            radius: Theme.px(1)
            color: row.markColor
        }

        Item {
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
                bottom: parent.bottom

                leftMargin: Theme.px(6) + root.depth * Theme.px(14)
                rightMargin: Theme.px(6)
            }

            clip: true

            Row {
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                }

                spacing: Theme.px(6)

                // -------------------------------------------------
                // Chevron expand/collapse — lebar tetap, hanya utk folder
                // -------------------------------------------------
                Item {
                    width: Theme.px(10)
                    height: Theme.px(10)
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        visible: root.isDir
                        anchors.centerIn: parent
                        text: root.expanded ? "▾" : "▸"
                        color: Theme.muted
                        font.pixelSize: Theme.fsSmall
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                // -------------------------------------------------
                // Icon: badge kecil, ukuran & posisi konsisten utk
                // semua baris (folder & file), warna beda per tipe
                // -------------------------------------------------
                Rectangle {
                    id: typeIcon
                    width: Theme.px(18)
                    height: Theme.px(16)
                    radius: Theme.px(4)
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.isDir
                        ? Qt.rgba(0.86, 0.65, 0.32, row.isSelected ? 0.28 : 0.16)
                        : Qt.rgba(1, 1, 1, 0.05)
                    border.color: root.isDir
                        ? Qt.rgba(0.86, 0.65, 0.32, 0.5)
                        : Theme.line
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: root.isDir ? "▣" : root.extBadge(root.name)
                        font.pixelSize: Theme.fsSmall * 0.62
                        font.bold: true
                        color: root.isDir ? "#d9a54a" : root.extColor(root.name)
                    }
                }

                // -------------------------------------------------
                // Nama file/folder
                // -------------------------------------------------
                Txt {
                    visible: !row.isEditing

                    text: root.name

                    font.pixelSize: Theme.fsSmall
                    font.bold: root.isDir

                    color:
                        root.isDir
                            ? Theme.text
                            : (row.active ? Theme.ink : Theme.muted)

                    elide: Text.ElideRight

                    anchors.verticalCenter: parent.verticalCenter
                }

                // -------------------------------------------------
                // Rename inline
                // -------------------------------------------------
                TextField {
                    id: renameField

                    visible: row.isEditing

                    text: root.name

                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsSmall

                    color: Theme.text

                    background: null

                    anchors.verticalCenter: parent.verticalCenter

                    function commitRename() {
                        if (!row.isEditing)
                            return

                        row.isEditing = false

                        var newName = text.trim()

                        if (
                            newName.length > 0 &&
                            newName !== root.name
                        ) {
                            root.requestRename(
                                root.path,
                                newName
                            )
                        } else {
                            text = root.name
                        }
                    }

                    Keys.onEscapePressed: {
                        row.isEditing = false
                        text = root.name
                    }

                    onAccepted: {
                        commitRename()
                    }

                    onActiveFocusChanged: {
                        if (!activeFocus && row.isEditing) {
                            commitRename()
                        }
                    }
                }
            }
        }

        // =========================================================
        // CONTEXT MENU
        // HANYA Rename + Delete
        // =========================================================
        Menu {
            id: contextMenu

            visible: false

            topPadding: Theme.px(4)
            bottomPadding: Theme.px(4)
            leftPadding: Theme.px(4)
            rightPadding: Theme.px(4)

            background: Rectangle {
                implicitWidth: Theme.px(140)

                color: Theme.cardSolid

                border.color: Theme.line
                border.width: 1

                radius: Theme.radiusSmall
            }

            // -----------------------------------------------------
            // Rename
            // -----------------------------------------------------
            MenuItem {
                id: miRename

                text: "Rename"

                height: Theme.px(28)

                contentItem: Txt {
                    text: miRename.text

                    font.pixelSize: Theme.fsSmall

                    color: Theme.text

                    verticalAlignment:
                        Text.AlignVCenter

                    leftPadding: Theme.px(8)
                }

                background: Rectangle {
                    radius: Theme.px(4)

                    color:
                        miRename.hovered
                            ? Theme.tintStrong
                            : "transparent"
                }

                onTriggered: {
                    row.isEditing = true

                    renameField.forceActiveFocus()

                    renameField.selectAll()
                }
            }

            // -----------------------------------------------------
            // Delete
            // -----------------------------------------------------
            MenuItem {
                id: miDelete

                text: "Delete"

                height: Theme.px(28)

                contentItem: Txt {
                    text: miDelete.text

                    font.pixelSize: Theme.fsSmall

                    color: Theme.warn

                    verticalAlignment:
                        Text.AlignVCenter

                    leftPadding: Theme.px(8)
                }

                background: Rectangle {
                    radius: Theme.px(4)

                    color:
                        miDelete.hovered
                            ? Theme.tintStrong
                            : "transparent"
                }

                onTriggered: {
                    root.requestDelete(root.path)
                }
            }
        }

        // =========================================================
        // Mouse
        // =========================================================
        MouseArea {
            id: area

            anchors.fill: parent

            hoverEnabled: true

            acceptedButtons:
                Qt.LeftButton | Qt.RightButton

            cursorShape:
                Qt.PointingHandCursor

            onClicked: (mouse) => {

                // Memindahkan active focus ke sini otomatis meng-commit
                // (jika terisi) atau membatalkan (jika kosong) input
                // rename/buat-baru yang mungkin sedang terbuka di baris lain.
                root.forceActiveFocus()

                root.selectItem(
                    root.path,
                    root.isDir
                )

                if (mouse.button === Qt.RightButton) {

                    if (root.path !== "") {
                        contextMenu.popup()
                    }

                } else {

                    root.toggle()

                }
            }
        }
    }

    // =============================================================
    // CHILDREN
    // =============================================================
    Column {
        id: kids

        width: root.width

        visible:
            root.isDir &&
            root.expanded

        // =========================================================
        // Input inline "buat baru" — muncul persis di lokasi folder
        // yang sedang aktif dibuat isinya (mirip VSCode: input tampil
        // sebagai baris anak di folder yang dipilih).
        // =========================================================
        Rectangle {
            id: createRow
            visible: root.showCreateHere
            width: kids.width
            height: visible ? Theme.px(28) : 0
            radius: Theme.px(4)
            color: Theme.tintStrong
            border.color: createInput.errorText.length > 0 ? Theme.warn : Theme.ink
            border.width: 1

            Row {
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    leftMargin: Theme.px(6) + (root.depth + 1) * Theme.px(14)
                    rightMargin: Theme.px(6)
                }
                height: Theme.px(28)
                spacing: Theme.px(6)

                Item { width: Theme.px(10); height: 1 }

                Rectangle {
                    width: Theme.px(18)
                    height: Theme.px(16)
                    radius: Theme.px(4)
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.creatingIsDir
                        ? Qt.rgba(0.86, 0.65, 0.32, 0.2)
                        : Qt.rgba(1, 1, 1, 0.05)
                    border.color: root.creatingIsDir ? Qt.rgba(0.86, 0.65, 0.32, 0.5) : Theme.line
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: root.creatingIsDir ? "▣" : "•"
                        font.pixelSize: Theme.fsSmall * 0.62
                        font.bold: true
                        color: root.creatingIsDir ? "#d9a54a" : Theme.muted
                    }
                }

                TextField {
                    id: createInput
                    width: parent.width - Theme.px(40)
                    anchors.verticalCenter: parent.verticalCenter
                    placeholderText: root.creatingIsDir ? "nama_folder" : "nama_file.ext"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsSmall
                    color: Theme.text
                    background: null

                    property string errorText: ""

                    function targetPath() {
                        var val = text.trim()
                        return root.creatingPath ? (root.creatingPath + "/" + val) : val
                    }

                    function validateNow() {
                        var val = text.trim()
                        if (val.length === 0) { errorText = ""; return }
                        if (root.creatingIsDir) {
                            errorText = editor.validateFolderName(targetPath())
                        } else if (val.endsWith(".")) {
                            errorText = "Nama file tidak boleh diakhiri dengan '.' tanpa ekstensi."
                        } else {
                            errorText = editor.validateFileName(targetPath())
                        }
                    }

                    onTextChanged: validateNow()

                    function commit() {
                        var val = text.trim()
                        if (val.length === 0) {
                            root.createFinished()
                            return
                        }
                        validateNow()
                        if (errorText.length > 0) {
                            root.createFinished()
                            return
                        }
                        root.beginCreate(targetPath())
                        if (root.creatingIsDir) {
                            editor.createFolder(targetPath())
                        } else {
                            editor.createFile(targetPath())
                            editor.openFile(targetPath())
                        }
                        root.createFinished()
                    }

                    onAccepted: commit()
                    Keys.onEscapePressed: root.createFinished()

                    onVisibleChanged: {
                        if (visible) {
                            text = ""
                            errorText = ""
                            forceActiveFocus()
                        }
                    }

                    onActiveFocusChanged: {
                        if (!activeFocus && visible) commit()
                    }
                }
            }
        }

        // Peringatan validasi nama file/folder — sebelumnya ditaruh di
        // DALAM createRow (yang tingginya tetap 28px), jadi malah
        // menumpuk & menutupi input alih-alih tampil di bawahnya.
        // Sekarang jadi item terpisah, sejajar dengan createRow di
        // dalam Column "kids", supaya otomatis muncul di bawahnya
        // tanpa menutupi apa pun.
        Rectangle {
            id: nameWarningInline
            visible: createInput.errorText.length > 0 && root.showCreateHere
            width: kids.width
            height: visible ? (warnText.implicitHeight + Theme.px(16)) : 0
            radius: Theme.radiusSmall
            color: Theme.cardSolid
            border.color: Theme.warn
            border.width: 1

            Txt {
                id: warnText
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    topMargin: Theme.px(8)
                    leftMargin: Theme.px(6) + (root.depth + 1) * Theme.px(14)
                    rightMargin: Theme.px(10)
                }
                text: createInput.errorText
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fsSmall * 0.9
                color: Theme.warn
            }
        }

        Repeater {
            model:
                root.isDir &&
                root.expanded
                    ? root.children
                    : []

            delegate: Loader {
                id: childLoader

                required property var modelData

                width: kids.width

                source:
                    Qt.resolvedUrl(
                        "FileTreeItem.qml"
                    )

                onLoaded: {

                    item.width =
                        Qt.binding(
                            function() {
                                return kids.width
                            }
                        )

                    item.name =
                        modelData.name

                    item.path =
                        modelData.path

                    item.isDir =
                        modelData.isDir

                    item.depth =
                        root.depth + 1

                    item.activePath =
                        Qt.binding(
                            function() {
                                return root.activePath
                            }
                        )

                    item.selectedPath =
                        Qt.binding(
                            function() {
                                return root.selectedPath
                            }
                        )

                    item.fileMarks =
                        Qt.binding(
                            function() {
                                return root.fileMarks
                            }
                        )

                    item.activeDirty =
                        Qt.binding(
                            function() {
                                return root.activeDirty
                            }
                        )

                    item.creatingActive =
                        Qt.binding(
                            function() {
                                return root.creatingActive
                            }
                        )

                    item.creatingPath =
                        Qt.binding(
                            function() {
                                return root.creatingPath
                            }
                        )

                    item.creatingIsDir =
                        Qt.binding(
                            function() {
                                return root.creatingIsDir
                            }
                        )

                    item.refreshToken =
                        Qt.binding(
                            function() {
                                return root.refreshToken
                            }
                        )

                    item.createFinished.connect(
                        function() {
                            root.createFinished()
                        }
                    )

                    item.beginCreate.connect(
                        function(p) {
                            root.beginCreate(p)
                        }
                    )

                    item.openFile.connect(
                        function(p) {
                            root.openFile(p)
                        }
                    )

                    item.selectItem.connect(
                        function(p, d) {
                            root.selectItem(p, d)
                        }
                    )

                    item.requestDelete.connect(
                        function(p) {
                            root.requestDelete(p)
                        }
                    )

                    item.requestCreate.connect(
                        function(parentP, d) {
                            root.requestCreate(
                                parentP,
                                d
                            )
                        }
                    )

                    item.requestRename.connect(
                        function(p, n) {
                            root.requestRename(
                                p,
                                n
                            )
                        }
                    )
                }
            }
        }
    }
}