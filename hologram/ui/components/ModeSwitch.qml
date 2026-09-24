import QtQuick
import "../theme"

// Tombol dua posisi Offline | Online. Online meredup kalau tidak ada internet.
Rectangle {
    id: root
    readonly property bool online: controller.mode === "online"

    implicitWidth: Theme.px(150)
    implicitHeight: Theme.px(32)
    radius: height / 2
    color: Theme.tint
    border.color: Theme.line
    border.width: 1

    Rectangle {
        id: thumb
        width: root.width / 2 - Theme.px(3)
        height: root.height - Theme.px(6)
        y: Theme.px(3)
        x: root.online ? root.width / 2 : Theme.px(3)
        radius: height / 2
        color: Theme.ink
        Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    }

    Row {
        anchors.fill: parent
        Item {
            width: parent.width / 2; height: parent.height
            Txt {
                anchors.centerIn: parent
                text: "OFFLINE"
                font.pixelSize: Theme.fsSmall
                font.bold: !root.online
                color: root.online ? Theme.muted : Theme.contrast
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: controller.setMode("offline") }
        }
        Item {
            width: parent.width / 2; height: parent.height
            opacity: controller.netOnline || root.online ? 1 : 0.55
            Txt {
                anchors.centerIn: parent
                text: "ONLINE"
                font.pixelSize: Theme.fsSmall
                font.bold: root.online
                color: root.online ? Theme.contrast : Theme.muted
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: controller.setMode("online") }
        }
    }
}
