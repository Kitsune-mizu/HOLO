import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "../theme"

// Info AI yang dipakai. Dengan internet: dropdown daftar model (tabel seperti `ollama list`).
// Tanpa internet: dropdown hilang, tersisa teks info.
Item {
    id: root
    property real popupWidth: Theme.px(340)
    readonly property bool interactive: controller.dropdownAvailable
    readonly property var fractions: controller.mode === "online" ? [0.46, 0.22, 0.32, 0] : [0.30, 0.30, 0.15, 0.25]
    readonly property real dotSize: Theme.px(8)
    readonly property real dotColumn: Theme.px(7) + dotSize + Theme.px(7)
    readonly property real cellsWidth: popupWidth - Theme.px(12) - dotColumn   // lebar popup dikurangi padding dan kolom titik

    implicitHeight: Theme.px(32)

    Txt {
        visible: !root.interactive
        anchors.fill: parent
        verticalAlignment: Text.AlignVCenter
        text: "AI: " + controller.aiInfo
        elide: Text.ElideRight
        color: Theme.muted
    }

    Rectangle {
        id: box
        visible: root.interactive
        anchors.fill: parent
        radius: Theme.radiusSmall
        color: area.containsMouse || popup.opened ? Theme.tintStrong : Theme.tint
        border.color: Theme.line
        border.width: 1
        Behavior on color { ColorAnimation { duration: Theme.fast } }

        Txt {
            anchors { left: parent.left; leftMargin: Theme.px(10); right: chevron.left; rightMargin: Theme.px(6); verticalCenter: parent.verticalCenter }
            text: "AI: " + controller.aiInfo
            elide: Text.ElideRight
        }
        Shape {
            id: chevron
            width: Theme.px(12); height: width
            anchors { right: parent.right; rightMargin: Theme.px(10); verticalCenter: parent.verticalCenter }
            rotation: popup.opened ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: Theme.fast } }
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.muted; strokeWidth: Theme.px(1.6); fillColor: "transparent"
                capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                startX: Theme.px(1.5); startY: Theme.px(4)
                PathLine { x: Theme.px(6); y: Theme.px(8.5) }
                PathLine { x: Theme.px(10.5); y: Theme.px(4) }
            }
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (popup.opened) { popup.close(); return }
                controller.refreshOptions()
                popup.open()
            }
        }
    }

    Popup {
        id: popup
        parent: root
        x: 0
        y: root.height + Theme.px(6)
        width: root.popupWidth
        padding: Theme.px(6)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }
        background: Rectangle { radius: Theme.radiusSmall; color: Theme.cardSolid; border.color: Theme.line; border.width: 1 }

        contentItem: Column {
            spacing: 0
            Row {   // judul kolom: NAME ID SIZE MODIFIED
                height: Theme.px(24)
                leftPadding: root.dotColumn
                Repeater {
                    model: controller.optionHeader
                    Txt {
                        width: root.cellsWidth * root.fractions[index]
                        height: parent.height
                        verticalAlignment: Text.AlignVCenter
                        text: modelData
                        font.pixelSize: Theme.fsSmall
                        color: Theme.dim
                    }
                }
            }
            Repeater {
                model: controller.options
                delegate: Rectangle {
                    id: rowItem
                    required property var modelData
                    readonly property bool chosen: modelData.id === controller.selectedOption
                    width: popup.width - popup.padding * 2
                    height: Theme.px(30)
                    radius: Theme.px(7)
                    color: rowArea.containsMouse ? Theme.tintStrong : rowItem.chosen ? Theme.tint : "transparent"

                    Row {
                        anchors.fill: parent
                        spacing: 0
                        Item {
                            width: root.dotColumn; height: parent.height
                            Rectangle {   // penanda: krem = muat di RAM, kuning = berat, kosong = tidak tersedia
                            width: root.dotSize; height: width; radius: width / 2
                            anchors.centerIn: parent
                            color: rowItem.modelData.tag === "ok" ? Theme.ink : rowItem.modelData.tag === "heavy" ? Theme.warn : "transparent"
                            border.color: rowItem.modelData.tag === "na" ? Theme.dim : "transparent"
                            border.width: 1
                            }
                        }
                        Repeater {
                            model: rowItem.modelData.cells
                            Txt {
                                width: root.cellsWidth * root.fractions[index]
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                text: modelData
                                elide: Text.ElideRight
                                font.pixelSize: Theme.fsSmall
                                font.bold: rowItem.chosen && index === 0
                                color: index === 0 ? Theme.text : Theme.muted
                            }
                        }
                    }
                    MouseArea {
                        id: rowArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { controller.selectOption(rowItem.modelData.id); popup.close() }
                    }
                }
            }
            Txt {
                visible: controller.mode === "offline"
                width: popup.width - popup.padding * 2
                topPadding: Theme.px(6)
                leftPadding: Theme.px(7)
                wrapMode: Text.Wrap
                text: "Titik krem: muat di RAM. Titik kuning: berat untuk RAM perangkat ini."
                font.pixelSize: Theme.fsSmall * 0.9
                color: Theme.dim
            }
        }
    }
}
