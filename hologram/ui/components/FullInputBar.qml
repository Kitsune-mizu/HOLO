import QtQuick
import QtQuick.Controls
import "../theme"

// Kartu input Mode AI. File terpisah dari InputBar.qml (punya HologramOS) karena backend-nya beda
// (`fullAI`, bukan `controller`) dan tidak ada mikrofon di sini - Mode AI ini teks-masuk/suara-keluar.
Rectangle {
    id: root
    radius: Theme.radius
    color: Theme.card
    border.color: Theme.line
    border.width: 1

    function send() {
        var t = field.text.trim()
        if (t.length === 0 || fullAI.busy) return
        fullAI.sendMessage(t)
        field.text = ""
    }

    Item {
        id: typing
        anchors.fill: parent
        opacity: fullAI.speaking ? 0 : 1
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        IconButton {
            id: voiceToggle
            icon: fullAI.voiceEnabled ? "speaker" : "speakeroff"
            anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.px(6) }
            onClicked: fullAI.toggleVoice()
        }
        TextField {
            id: field
            anchors { left: voiceToggle.right; right: sendButton.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.px(4) }
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsBody
            color: Theme.text
            placeholderText: "Tanya apa saja ke AI..."
            placeholderTextColor: Theme.dim
            selectionColor: Theme.tintStrong
            selectedTextColor: Theme.text
            selectByMouse: true
            background: null
            onAccepted: root.send()
        }
        IconButton {
            id: sendButton
            icon: "send"
            enabled: field.text.trim().length > 0 && !fullAI.busy
            anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: Theme.px(8) }
            onClicked: root.send()
        }
    }

    VoiceBar {
        anchors.fill: parent
        level: fullAI.level
        active: fullAI.speaking
        opacity: fullAI.speaking ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: fullAI.stopSpeaking() }
    }
}
