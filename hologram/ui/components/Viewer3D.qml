import QtQuick
import QtQuick3D
import QtQuick3D.AssetUtils
import "../theme"
import "../Quat.js" as Quat

// Tampilan utama: grid, model 3D (Qt Quick 3D + RuntimeLoader untuk .glb), dan nama model.
Item {
    id: root

    readonly property real modelSize: 140          // ukuran terpanjang model, dalam satuan scene
    readonly property real baseDistance: 420
    readonly property real lift: 0.09              // model naik sekian bagian tinggi dari tengah layar
    readonly property bool wireframe: viewCfg.wireframe
    readonly property real lineScale: wireframe ? Math.max(2, Math.round(Theme.u * 2)) : 1

    // Zoom
    property real zoomGoal: 1
    property real zoom: 1
    Behavior on zoom { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
    onZoomGoalChanged: zoom = zoomGoal
    function zoomBy(factor) { zoomGoal = Math.max(0.45, Math.min(2.4, zoomGoal * factor)) }

    // Rotasi: dari qFrom ke qTo lewat slerp, dengan easing supaya berhenti pelan.
    property var qFrom: Quat.start()
    property var qTo: Quat.start()
    property real turnT: 1
    readonly property var currentRot: Quat.slerp(qFrom, qTo, turnT)
    NumberAnimation { id: turnAnim; target: root; property: "turnT"; from: 0; to: 1; duration: 650; easing.type: Easing.OutCubic }
    function rotate(direction) {
        qFrom = currentRot
        qTo = Quat.mul(Quat.step(direction, viewCfg.rotateStep), qTo)
        turnAnim.restart()
    }
    // Putaran halus dan menerus (gesture tangan): tidak ada animasi easing, tiap panggilan langsung menambah sudut,
    // supaya kecepatan benar-benar mengikuti kemiringan telunjuk saat ini, bukan mengejar target lama.
    function spin(yawDeg, pitchDeg) {
        turnAnim.stop()
        var q = Quat.mul(Quat.axisAngle(0, 1, 0, yawDeg), Quat.mul(Quat.axisAngle(1, 0, 0, pitchDeg), currentRot))
        qFrom = q; qTo = q; turnT = 1
    }

    // Kendali mouse: seret untuk memutar (kiri-kanan = yaw, atas-bawah = pitch), scroll untuk zoom.
    // Ini jalur kendali terpisah dari gesture tangan, dan selalu tersedia (mis. kamera mati atau tanpa kamera).
    readonly property real dragDegPerPixel: 0.35
    DragHandler {
        id: dragHandler
        target: null
        property point prevTranslation: Qt.point(0, 0)
        onActiveChanged: prevTranslation = Qt.point(0, 0)
        onTranslationChanged: {
            var dx = translation.x - prevTranslation.x
            var dy = translation.y - prevTranslation.y
            prevTranslation = translation
            root.spin(dx * root.dragDegPerPixel, dy * root.dragDegPerPixel)
        }
    }
    WheelHandler {
        id: wheelHandler
        target: null
        onWheel: (event) => root.zoomBy(event.angleDelta.y > 0 ? 1.12 : 1 / 1.12)
    }

    // Putaran pelan saat diam
    property real idleAngle: 0
    NumberAnimation on idleAngle {
        from: 0; to: 360
        duration: viewCfg.idleSpin > 0 ? 360000 / viewCfg.idleSpin : 1000
        loops: Animation.Infinite
        running: viewCfg.idleSpin > 0
    }

    // Ukuran model dari bounds RuntimeLoader
    readonly property vector3d bMin: loader.bounds.minimum
    readonly property vector3d bMax: loader.bounds.maximum
    readonly property real extent: Math.max(bMax.x - bMin.x, bMax.y - bMin.y, bMax.z - bMin.z)
    readonly property bool ready: loader.status === RuntimeLoader.Success && extent > 0
    readonly property real fit: ready ? modelSize / extent : 1
    property real appear: 1
    onReadyChanged: if (ready) appearAnim.restart()
    NumberAnimation { id: appearAnim; target: root; property: "appear"; from: 0.6; to: 1; duration: 380; easing.type: Easing.OutCubic }

    Connections {
        target: controller
        function onViewCommand(name, arg) {
            if (name === "rotate") root.rotate(arg)
            else if (name === "spin") { var sp = arg.split(","); root.spin(parseFloat(sp[0]), parseFloat(sp[1])) }
            else if (name === "zoom") root.zoomBy(parseFloat(arg))
            else if (name === "resetZoom") root.zoomGoal = 1
        }
        function onSnapshotRequested(path) {
            capture.grabToImage(function(result) { controller.snapshotSaved(result.saveToFile(path)) })
        }
    }

    // Semua yang ikut ditangkap untuk AI online: latar, grid, dan model.
    Item {
        id: capture
        anchors.fill: parent

        Rectangle { anchors.fill: parent; color: Theme.bg }

        Item {
            id: grid
            anchors.fill: parent
            readonly property real step: Theme.px(60)
            Repeater {
                model: Math.ceil(root.width / grid.step) + 1
                Rectangle { x: Math.round(index * grid.step); width: 1; height: grid.height; color: Theme.grid }
            }
            Repeater {
                model: Math.ceil(root.height / grid.step) + 1
                Rectangle { y: Math.round(index * grid.step); width: grid.width; height: 1; color: Theme.grid }
            }
        }

        // Mode kawat digambar lebih kecil lalu diperbesar, supaya garisnya tebal seperti gambar referensi.
        View3D {
            id: view
            width: capture.width / root.lineScale
            height: capture.height / root.lineScale
            scale: root.lineScale
            transformOrigin: Item.TopLeft

            environment: SceneEnvironment {
                clearColor: "transparent"
                backgroundMode: SceneEnvironment.Transparent
                antialiasingMode: SceneEnvironment.MSAA
                antialiasingQuality: SceneEnvironment.High
                debugSettings.wireframeEnabled: root.wireframe
            }

            PerspectiveCamera {
                readonly property real dist: root.baseDistance / root.zoom
                position: Qt.vector3d(0, -dist * 2 * root.lift * 0.5774, dist)
                clipNear: 10
                clipFar: 4000
            }
            DirectionalLight { eulerRotation.x: -28; eulerRotation.y: -32; brightness: 1.1 }

            Node {
                rotation: Qt.quaternion(root.currentRot.w, root.currentRot.x, root.currentRot.y, root.currentRot.z)
                Node {
                    eulerRotation.y: root.idleAngle
                    Node {
                        visible: root.ready
                        readonly property real s: root.fit * root.appear
                        scale: Qt.vector3d(s, s, s)
                        position: Qt.vector3d(-(root.bMin.x + root.bMax.x) / 2 * s,
                                              -(root.bMin.y + root.bMax.y) / 2 * s,
                                              -(root.bMin.z + root.bMax.z) / 2 * s)
                        RuntimeLoader {
                            id: loader
                            source: controller.modelSource
                            onStatusChanged: if (status === RuntimeLoader.Error) controller.modelStatus(false, errorString)
                        }
                    }
                }
            }
        }
    }

    Txt {
        text: controller.shapeName.toUpperCase()
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.66
        font.pixelSize: Theme.fsLabel
        font.letterSpacing: Theme.px(1.5)
        color: Theme.text
        opacity: 0.85
    }
}
