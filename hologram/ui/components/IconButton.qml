import QtQuick
import QtQuick.Shapes
import "../theme"

// Tombol bulat dengan ikon garis. Ikon digambar dari path SVG 24x24, tanpa file gambar.
Item {
    id: root
    property string icon: "send"
    property bool active: false
    property real size: Theme.px(34)
    signal clicked()

    readonly property var icons: ({
        send: ["M21 3.5 L3 11 L10.5 13.5 L13 21 Z", "M21 3.5 L10.5 13.5", "", ""],
        mic: ["M12 3.5 a3 3 0 0 1 3 3 V11 a3 3 0 0 1 -6 0 V6.5 a3 3 0 0 1 3 -3 Z", "M6.5 11 a5.5 5.5 0 0 0 11 0", "M12 16.5 V20.5", "M9 20.5 H15"],
        down: ["M6 9.5 L12 15.5 L18 9.5", "", "", ""],
        cam: ["M2.5 7.5 H14.5 V16.5 H2.5 Z", "M14.5 11 L21.5 7.5 V16.5 L14.5 13 Z", "", ""],
        camoff: ["M2.5 7.5 H14.5 V16.5 H2.5 Z", "M14.5 11 L21.5 7.5 V16.5 L14.5 13 Z", "M3.5 3.5 L20.5 20.5", ""],
        speaker: ["M4 9.5 H8 L13.5 5 V19 L8 14.5 H4 Z", "M17 9 A5 5 0 0 1 17 15", "M19.5 6.5 A9 9 0 0 1 19.5 17.5", ""],
        speakeroff: ["M4 9.5 H8 L13.5 5 V19 L8 14.5 H4 Z", "M17 9 L21.5 15", "M21.5 9 L17 15", ""]
    })
    readonly property color tone: !enabled ? Theme.dim : active ? Theme.contrast : Theme.text

    implicitWidth: size
    implicitHeight: size
    opacity: enabled ? 1 : 0.5

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: root.active ? Theme.ink : area.pressed ? Theme.tintStrong : area.containsMouse ? Theme.tint : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    Shape {
        width: 24; height: 24
        anchors.centerIn: parent
        scale: root.size * 0.5 / 24
        preferredRendererType: Shape.CurveRenderer
        ShapePath { strokeColor: root.tone; strokeWidth: 1.8; fillColor: "transparent"; capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.icons[root.icon][0] } }
        ShapePath { strokeColor: root.tone; strokeWidth: 1.8; fillColor: "transparent"; capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.icons[root.icon][1] } }
        ShapePath { strokeColor: root.tone; strokeWidth: 1.8; fillColor: "transparent"; capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.icons[root.icon][2] } }
        ShapePath { strokeColor: root.tone; strokeWidth: 1.8; fillColor: "transparent"; capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.icons[root.icon][3] } }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
