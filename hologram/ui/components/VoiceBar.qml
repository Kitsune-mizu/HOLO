import QtQuick
import "../theme"

// Bar suara pengganti kolom input saat AI berbicara. Tinggi batang mengikuti level suara asli.
Item {
    id: root
    property real level: 0
    property bool active: false
    property real phase: 0

    Timer {
        interval: 33
        repeat: true
        running: root.active
        onTriggered: root.phase += 0.35
    }

    Row {
        anchors.centerIn: parent
        spacing: Theme.px(4)
        Repeater {
            model: 30
            Rectangle {
                readonly property real wave: 0.35 + 0.65 * Math.abs(Math.sin(root.phase + index * 0.55))
                width: Theme.px(3)
                radius: width / 2
                anchors.verticalCenter: parent.verticalCenter
                height: Theme.px(4) + (root.height * 0.62 - Theme.px(4)) * Math.min(1, root.level * wave * 1.15)
                color: Theme.ink
                opacity: 0.55 + 0.45 * root.level
            }
        }
    }
}
