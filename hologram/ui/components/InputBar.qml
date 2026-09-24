import QtQuick
import QtQuick.Controls
import "../theme"

// Kartu input: teks, mikrofon, kirim. Saat AI berbicara berubah menjadi bar suara.
Rectangle {
    id: root
    radius: Theme.radius
    color: Theme.card
    border.color: Theme.line
    border.width: 1

    function send() {
        var t = field.text.trim()
        if (t.length === 0 || controller.busy) return
        controller.sendMessage(t)
        field.text = ""
    }

    Connections {
        target: controller
        function onTranscriptReady(text) { field.text = text; root.send() }
    }

    Item {
        id: typing
        anchors.fill: parent
        opacity: controller.speaking ? 0 : 1
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        IconButton {
            id: voiceToggle
            icon: controller.voiceEnabled ? "speaker" : "speakeroff"
            anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.px(6) }
            onClicked: controller.toggleVoice()
        }
        TextField {
            id: field
            anchors { left: voiceToggle.right; right: mic.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.px(4) }
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsBody
            color: Theme.text
            placeholderText: controller.listening ? "Mendengarkan..." : "Tulis perintah atau pertanyaan"
            placeholderTextColor: controller.listening ? Theme.ink : Theme.dim
            selectionColor: Theme.tintStrong
            selectedTextColor: Theme.text
            selectByMouse: true
            background: null
            onAccepted: root.send()
        }
        IconButton {
            id: mic
            icon: "mic"
            active: controller.listening
            anchors { right: sendButton.left; verticalCenter: parent.verticalCenter; rightMargin: Theme.px(2) }
            onClicked: controller.toggleMic()
        }
        IconButton {
            id: sendButton
            icon: "send"
            enabled: field.text.trim().length > 0 && !controller.busy
            anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: Theme.px(8) }
            onClicked: root.send()
        }
    }

    VoiceBar {
        anchors.fill: parent
        level: controller.level
        active: controller.speaking
        opacity: controller.speaking ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: controller.stopSpeaking() }
    }
}
