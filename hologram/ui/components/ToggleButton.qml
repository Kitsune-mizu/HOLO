import QtQuick
import QtQuick.Shapes
import "../theme"

// Pil kecil: teks dan, kalau diminta, panah yang berbalik saat `checked` berubah.
Item {
    id: root
    property string text: ""
    property bool checked: true
    property bool showChevron: false
    property bool pointUp: false          // panah menghadap atas saat terbuka (untuk panel yang menyusut ke atas)
    signal clicked()

    implicitHeight: Theme.px(28)
    implicitWidth: row.implicitWidth + Theme.px(26)

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: area.pressed ? Theme.tintStrong : area.containsMouse ? Theme.tintStrong : Theme.tint
        border.color: Theme.line
        border.width: 1
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Theme.px(8)

        Rectangle {          // titik status, terisi saat aktif
            visible: !root.showChevron
            width: Theme.px(8); height: width; radius: width / 2
            anchors.verticalCenter: parent.verticalCenter
            color: root.checked ? Theme.ink : "transparent"
            border.color: root.checked ? Theme.ink : Theme.muted
            border.width: 1
        }
        Txt {
            text: root.text
            font.pixelSize: Theme.fsSmall
            color: Theme.text
            anchors.verticalCenter: parent.verticalCenter
        }
        Shape {
            visible: root.showChevron
            width: Theme.px(12); height: width
            anchors.verticalCenter: parent.verticalCenter
            rotation: root.checked !== root.pointUp ? 0 : 180
            Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.text; strokeWidth: Theme.px(1.6); fillColor: "transparent"
                capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                startX: Theme.px(1.5); startY: Theme.px(4)
                PathLine { x: Theme.px(6); y: Theme.px(8.5) }
                PathLine { x: Theme.px(10.5); y: Theme.px(4) }
            }
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
