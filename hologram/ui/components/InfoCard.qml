import QtQuick
import "../theme"

// Info penting tepat di atas kartu kamera: AI yang dipakai, mode, internet, FPS, tangan, RAM.
Rectangle {
    id: root
    property real fps: 0

    readonly property string handText: {
        if (controller.cameraFrame === 0 && controller.cameraStatus !== "") return "kamera mati"
        if (controller.gesture !== "") return controller.gesture
        if (controller.handState === "pinch") return "dua tangan (zoom)"
        if (controller.handState === "point_two") return "dua jari + telunjuk"
        if (controller.handState === "two") return "dua jari"
        if (controller.handState === "point") return "menunjuk"
        if (controller.handState === "open") return "terbuka"
        if (controller.handState === "closed") return "tertutup"
        return "tidak terlihat"
    }

    implicitHeight: rows.implicitHeight + Theme.px(22)
    radius: Theme.radius
    color: Theme.card
    border.color: Theme.line
    border.width: 1

    component Row2: Item {
        property string label
        property string value
        property color tone: Theme.text
        width: parent.width
        height: Theme.px(18)
        Txt { text: parent.label; color: Theme.dim; font.pixelSize: Theme.fsSmall; anchors.verticalCenter: parent.verticalCenter }
        Txt {
            text: parent.value
            color: parent.tone
            font.pixelSize: Theme.fsSmall
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignRight
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            width: parent.width * 0.68
        }
    }

    Column {
        id: rows
        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: Theme.px(14) }
        spacing: Theme.px(2)
        Row2 { label: "AI"; value: controller.aiInfo }
        Row2 { label: "MODE"; value: controller.mode === "online" ? "Online" : "Offline" }
        Row2 { label: "INTERNET"; value: controller.netOnline ? "tersambung" : "terputus"; tone: controller.netOnline ? Theme.text : Theme.warn }
        Row2 { label: "FPS"; value: root.fps.toFixed(1) }
        Row2 { label: "TANGAN"; value: root.handText; tone: controller.gesture !== "" ? Theme.ink : Theme.text }
        Row2 { label: "RAM"; value: controller.ramText === "" ? "-" : controller.ramText }
    }
}
