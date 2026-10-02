import QtQuick
import QtQuick.Effects
import "../theme"

// Kamera asli, filter abu, kerangka tangan. Sudut bulat. Pesan kalau kamera atau deteksi tidak siap.
Rectangle {
    id: root
    readonly property real frameWidth: Math.max(1, Math.round(Theme.px(2)))
    readonly property bool hasFrame: controller.cameraFrame > 0 && controller.cameraStatus === ""

    radius: Theme.radius
    color: "#000000"
    border.color: Theme.muted
    border.width: frameWidth

    Image {
        id: picture
        anchors.fill: parent
        anchors.margins: root.frameWidth
        visible: false
        cache: false
        asynchronous: false
        fillMode: Image.PreserveAspectCrop
        source: controller.cameraFrame > 0 ? "image://camera/" + controller.cameraFrame : ""
    }
    Item {
        id: roundMask
        anchors.fill: picture
        visible: false
        layer.enabled: true
        Rectangle { anchors.fill: parent; radius: root.radius - root.frameWidth; color: "black" }
    }
    MultiEffect {
        anchors.fill: picture
        source: picture
        maskEnabled: true
        maskSource: roundMask
        visible: controller.cameraFrame > 0 && picture.status === Image.Ready
    }

    Rectangle {          // pesan di bawah gambar kalau kamera hidup tapi deteksi tangan bermasalah
        visible: controller.cameraStatus !== "" && controller.cameraFrame > 0
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: root.frameWidth }
        height: note.implicitHeight + Theme.px(14)
        radius: root.radius - root.frameWidth
        color: Qt.rgba(0, 0, 0, 0.72)
        Txt { id: note; anchors { fill: parent; margins: Theme.px(7) } text: controller.cameraStatus; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.fsSmall; color: Theme.warn }
    }
    Rectangle {          // tombol kecil hidup/mati kamera di pojok kanan atas
        id: cameraSwitch
        width: Theme.px(30); height: width; radius: width / 2
        anchors { top: parent.top; right: parent.right; margins: Theme.px(9) }
        color: Qt.rgba(0, 0, 0, 0.6)
        border.color: controller.cameraOn ? Theme.line : Theme.warn
        border.width: 1
        IconButton {
            anchors.centerIn: parent
            size: Theme.px(28)
            icon: controller.cameraOn ? "cam" : "camoff"
            onClicked: controller.toggleCamera()
        }
    }
    Txt {                // kamera belum ada gambar sama sekali
        visible: controller.cameraFrame === 0
        anchors { fill: parent; margins: Theme.px(16) }
        text: controller.cameraStatus !== "" ? controller.cameraStatus : "Menunggu kamera..."
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font.pixelSize: Theme.fsSmall
        color: controller.cameraStatus !== "" ? Theme.warn : Theme.dim
    }
}
