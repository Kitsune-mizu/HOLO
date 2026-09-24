import QtQuick
import "../theme"

// Kartu percakapan: dropdown model + Offline/Online di atas, pesan di bawahnya.
// `shown` false: kartu meluncur turun ke balik tombol dan input. `shown` true: meluncur naik.
Item {
    id: root
    property bool shown: true
    clip: true

    Rectangle {
        id: card
        width: root.width
        height: root.height
        y: root.shown ? 0 : root.height + Theme.px(6)
        opacity: root.shown ? 1 : 0
        visible: y < root.height
        radius: Theme.radius
        color: Theme.card
        border.color: Theme.line
        border.width: 1
        Behavior on y { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        Item {
            id: head
            height: Theme.px(34)
            anchors { top: parent.top; left: parent.left; right: parent.right; margins: Theme.px(10) }
            ModeSwitch {
                id: modeSwitch
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                width: Theme.px(150)
                height: Theme.px(30)
            }
            ModelDropdown {
                anchors { left: parent.left; right: modeSwitch.left; rightMargin: Theme.px(8); verticalCenter: parent.verticalCenter }
                height: Theme.px(30)
                popupWidth: card.width - Theme.px(20)
            }
        }
        Rectangle {
            id: divider
            anchors { top: head.bottom; topMargin: Theme.px(6); left: parent.left; right: parent.right; margins: Theme.px(10) }
            height: 1
            color: Theme.line
        }

        ListView {
            id: list
            anchors { top: divider.bottom; topMargin: Theme.px(6); left: parent.left; right: parent.right; bottom: parent.bottom; margins: Theme.px(10) }
            clip: true
            spacing: Theme.px(7)
            model: messageModel
            boundsBehavior: Flickable.StopAtBounds

            onCountChanged: Qt.callLater(list.positionViewAtEnd)
            onContentHeightChanged: if (atYEnd || count < 3) Qt.callLater(list.positionViewAtEnd)

            delegate: Item {
                id: entry
                required property string role
                required property string text
                readonly property real maxWidth: list.width * 0.88
                width: list.width
                height: bubble.height

                TextMetrics { id: metrics; font: body.font; text: entry.text }

                Rectangle {
                    id: bubble
                    width: entry.role === "system" ? list.width : Math.min(entry.maxWidth, metrics.advanceWidth + Theme.px(24))
                    height: body.implicitHeight + (entry.role === "system" ? Theme.px(2) : Theme.px(16))
                    x: entry.role === "user" ? list.width - width : entry.role === "ai" ? 0 : 0
                    radius: Theme.px(12)
                    color: entry.role === "user" ? Theme.tintStrong : entry.role === "ai" ? Theme.tint : "transparent"
                    border.color: entry.role === "ai" ? Theme.line : "transparent"
                    border.width: 1

                    Txt {
                        id: body
                        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                                  leftMargin: entry.role === "system" ? 0 : Theme.px(12); rightMargin: entry.role === "system" ? 0 : Theme.px(12) }
                        text: entry.text
                        wrapMode: Text.Wrap
                        horizontalAlignment: entry.role === "system" ? Text.AlignHCenter : Text.AlignLeft
                        font.pixelSize: entry.role === "system" ? Theme.fsSmall : Theme.fsBody
                        font.italic: entry.role === "system"
                        color: entry.role === "system" ? Theme.muted : Theme.text
                    }
                }
            }

            footer: Item {
                width: list.width
                height: controller.busy ? Theme.px(26) : 0
                clip: true
                Txt {
                    id: thinking
                    anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.px(4) }
                    property int dots: 0
                    text: "AI sedang berpikir" + ".".repeat(dots)
                    font.pixelSize: Theme.fsSmall
                    color: Theme.muted
                    Timer { interval: 400; repeat: true; running: controller.busy; onTriggered: thinking.dots = (thinking.dots + 1) % 4 }
                }
            }
        }
    }
}
