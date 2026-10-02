import QtQuick
import "../theme"

// Kartu percakapan Mode AI. SENGAJA file terpisah dari ChatPanel.qml (punya HologramOS): model
// pesannya beda (`fullMessages`, bukan `messageModel`), dan header-nya hanya pemilih ENGINE AI -
// tanpa Offline/Online sama sekali, karena Mode AI ini murni online.
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

            Txt { text: "MODE AI"; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: Theme.fsSmall; font.letterSpacing: Theme.px(1); color: Theme.muted }

            Row {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: Theme.px(8)
                // Token yang SUDAH terpakai sesi ini (dari respons Gemini sendiri, akumulasi) -
                // bukan "sisa kuota", karena Gemini tidak punya endpoint publik untuk itu di API key biasa.
                Txt {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Gemini" + (fullAI.tokensUsed > 0 ? " · " + fullAI.tokensUsed + " token" : "")
                    font.pixelSize: Theme.fsSmall
                    color: Theme.muted
                }
                IconButton {
                    icon: "trash"
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: fullAI.clearHistory()
                }
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
            model: fullMessages
            boundsBehavior: Flickable.StopAtBounds

            onCountChanged: Qt.callLater(list.positionViewAtEnd)
            onContentHeightChanged: if (atYEnd || count < 3) Qt.callLater(list.positionViewAtEnd)

            delegate: Item {
                id: entry
                required property string role
                required property string text
                // Bubble AI dibolehkan lebih lebar (0.94 vs 0.88 di ChatPanel) karena balasan Mode AI
                // boleh panjang/mendalam - dipersempit sedikit lagi khusus utuk bubble user agar tetap enak dibaca.
                readonly property real maxWidth: list.width * (entry.role === "ai" ? 0.94 : 0.82)
                width: list.width
                height: bubble.height

                TextMetrics { id: metrics; font: body.font; text: entry.text }

                Rectangle {
                    id: bubble
                    width: entry.role === "system" ? list.width : Math.min(entry.maxWidth, metrics.advanceWidth + Theme.px(24))
                    height: body.implicitHeight + (entry.role === "system" ? Theme.px(2) : Theme.px(16))
                    x: entry.role === "user" ? list.width - width : 0
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
                height: fullAI.busy ? Theme.px(26) : 0
                clip: true
                Txt {
                    anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.px(4) }
                    property int dots: 0
                    text: "AI sedang berpikir" + ".".repeat(dots)
                    font.pixelSize: Theme.fsSmall
                    color: Theme.muted
                    Timer { interval: 400; repeat: true; running: fullAI.busy; onTriggered: parent.dots = (parent.dots + 1) % 4 }
                }
            }
        }
    }
}
