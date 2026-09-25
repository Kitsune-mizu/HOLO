import QtQuick
import QtQuick.Window
import "theme"
import "components"

// Jendela utama. Kiri: judul, chat, input. Tengah: model 3D. Kanan bawah: info dan kamera.
Window {
    id: win
    width: viewCfg.initialWidth
    height: viewCfg.initialHeight
    minimumWidth: 640
    minimumHeight: 400
    visible: true
    title: "Hologram OS"
    color: Theme.bg

    property bool chatOpen: true      // seluruh sisi kiri
    property bool convOpen: true      // kartu percakapan saja
    property bool sideOpen: true      // seluruh sisi kanan: info + kamera
    property bool infoOpen: true      // kartu info saja
    property bool codeOpen: false     // panel editor kode (overlay penuh)
    property real fps: 0
    property int frames: 0

    Binding { target: Theme; property: "viewportW"; value: win.width }
    Binding { target: Theme; property: "viewportH"; value: win.height }

    Connections { target: win; function onFrameSwapped() { win.frames++ } }
    Timer {
        interval: 500; repeat: true; running: true
        onTriggered: { win.fps = win.frames * 2; win.frames = 0 }
    }

    Viewer3D { anchors.fill: parent }

    // Judul dan tombol chat
    Column {
        id: header
        x: Theme.margin
        y: Theme.margin
        spacing: Theme.px(2)
        Txt { text: "HOLOGRAM OS"; font.pixelSize: Theme.fsTitle; font.bold: true; font.letterSpacing: Theme.px(1); color: Theme.ink }
        Txt { text: "SHAPE: " + controller.shapeName.toUpperCase(); font.pixelSize: Theme.px(15); color: Theme.muted }
    }
    Row {
        anchors { left: header.right; leftMargin: Theme.px(20); verticalCenter: header.verticalCenter }
        spacing: Theme.px(8)
        ToggleButton {
            text: "CHAT"
            checked: win.chatOpen
            onClicked: win.chatOpen = !win.chatOpen
        }
        ToggleButton {
            text: "KODE"
            checked: win.codeOpen
            onClicked: win.codeOpen = !win.codeOpen
        }
    }

    // Kiri: chat AI
    Item {
        id: left
        width: Math.min(Theme.px(388), win.width * 0.46)
        anchors { top: header.bottom; topMargin: Theme.px(14); bottom: parent.bottom; bottomMargin: Theme.margin }
        x: win.chatOpen ? Theme.margin : -width - Theme.margin
        opacity: win.chatOpen ? 1 : 0
        visible: opacity > 0.01
        Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        ChatPanel {
            anchors { left: parent.left; right: parent.right; bottom: hideButton.top; bottomMargin: Theme.gap }
            height: Math.max(0, Math.min(left.height - hideButton.height - inputBar.height - Theme.gap * 3, Theme.px(420)))
            shown: win.convOpen
        }
        ToggleButton {
            id: hideButton
            anchors { left: parent.left; bottom: inputBar.top; bottomMargin: Theme.gap }
            text: win.convOpen ? "Sembunyikan percakapan" : "Tampilkan percakapan"
            showChevron: true
            checked: win.convOpen
            onClicked: win.convOpen = !win.convOpen
        }
        InputBar {
            id: inputBar
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: Theme.px(48)
        }
    }

    // Kanan atas: tombol untuk menyembunyikan seluruh sisi kanan (info + kamera), seperti tombol CHAT di kiri.
    ToggleButton {
        anchors { right: parent.right; rightMargin: Theme.margin; verticalCenter: header.verticalCenter }
        text: "KAMERA"
        checked: win.sideOpen
        onClicked: win.sideOpen = !win.sideOpen
    }

    // Kanan bawah: tombol sembunyikan info, kartu info, lalu kartu kamera. Seluruhnya meluncur ke kanan saat disembunyikan.
    Column {
        id: side
        readonly property real cardWidth: Math.min(Theme.px(360), win.width * 0.34)
        width: cardWidth
        spacing: Theme.px(10)
        x: win.sideOpen ? win.width - width - Theme.margin : win.width + Theme.margin
        y: win.height - height - Theme.margin
        opacity: win.sideOpen ? 1 : 0
        visible: opacity > 0.01
        Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        ToggleButton {
            anchors.right: parent.right
            text: win.infoOpen ? "Sembunyikan info" : "Tampilkan info"
            showChevron: true
            pointUp: true
            checked: win.infoOpen
            onClicked: win.infoOpen = !win.infoOpen
        }
        Item {                      // ruang kartu info: menyusut ke nol, kartunya meluncur naik dan terpotong
            width: parent.width
            height: win.infoOpen ? info.height : 0
            clip: true
            Behavior on height { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
            InfoCard {
                id: info
                width: parent.width
                fps: win.fps
                y: win.infoOpen ? 0 : -height
                opacity: win.infoOpen ? 1 : 0
                Behavior on y { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: Theme.normal } }
            }
        }
        CameraCard { width: parent.width; height: width * 9 / 16 }
    }

    // Editor kode: overlay besar di atas semuanya, supaya ada cukup ruang untuk pohon file + isi file.
    // Latar gelap dulu (klik di luar panel = tutup), baru panelnya di atas supaya menerima kliknya sendiri.
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.55)
        visible: win.codeOpen
        opacity: win.codeOpen ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        MouseArea { anchors.fill: parent; onClicked: win.codeOpen = false }
    }
    CodeEditorPanel {
        anchors.centerIn: parent
        width: Math.min(win.width - Theme.margin * 2, Theme.px(1040))
        height: Math.min(win.height - Theme.margin * 2, Theme.px(680))
        scale: win.codeOpen ? 1 : 0.96
        opacity: win.codeOpen ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    }
}
