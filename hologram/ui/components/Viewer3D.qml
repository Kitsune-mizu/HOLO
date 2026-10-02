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
    readonly property real lift: 0                 // model di tengah layar (tidak ada lagi label di bawah yang perlu ruang)
    property bool wireframe: viewCfg.wireframe     // nilai awal dari config.toml, sekarang bisa di-toggle tombol
    readonly property real lineScale: wireframe ? Math.max(2, Math.round(Theme.u * 2)) : 1

    // Zoom
    property real zoomGoal: 1
    property real zoom: 1
    Behavior on zoom { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
    onZoomGoalChanged: zoom = zoomGoal
    property real maxZoom: 3
    function zoomBy(factor) {
        // Pengaman: kalau factor bukan angka valid (mis. dari binding yang salah), abaikan saja
        // daripada zoomGoal jadi NaN/Infinity dan kamera rusak.
        if (typeof factor !== "number" || !isFinite(factor) || factor <= 0) return
        zoomGoal = Math.max(0.12, Math.min(root.maxZoom, zoomGoal * factor))
    }
    function setMaxZoom(z) {
        // Pengaman: tolak nilai yang tidak masuk akal, biarkan maxZoom sebelumnya tetap berlaku.
        if (typeof z !== "number" || !isFinite(z) || z <= 0) return
        root.maxZoom = z
        zoomGoal = Math.min(zoomGoal, z)
    }

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

    // Mode diam: saat true, orbit otomatis (idle spin) dihentikan/dibekukan di sudut saat ini.
    // Kendali manual (drag mouse, gesture tangan, tombol rotate) tetap jalan seperti biasa.
    property bool stillMode: false

    // Putaran pelan saat diam
    property real idleAngle: 0
    NumberAnimation on idleAngle {
        from: 0; to: 360
        duration: viewCfg.idleSpin > 0 ? 360000 / viewCfg.idleSpin : 1000
        loops: Animation.Infinite
        running: viewCfg.idleSpin > 0 && !root.stillMode
    }

    // Ukuran model dari bounds RuntimeLoader.
    // PENTING: bounds di-"bekukan" sekali saat model selesai dimuat, bukan dibind langsung ke
    // loader.bounds. Model statis bounds-nya memang tidak berubah, tapi model berskin/beranimasi
    // (mis. hornet_silksong.glb) punya bounds yang berubah TIAP FRAME mengikuti pose animasinya.
    // Kalau scale & posisi ikut dihitung ulang tiap frame dari bounds yang bergerak itu, seluruh
    // model jadi terlihat berkelebaran/glitch (ukuran & posisi re-center-nya "berkedut" mengikuti
    // silhouette animasi). Dengan membekukan bounds, animasi tulang/joint tetap main normal, tapi
    // skala & titik pusat model tetap stabil.
    property vector3d bMin: Qt.vector3d(0, 0, 0)
    property vector3d bMax: Qt.vector3d(0, 0, 0)
    property real extent: 0
    readonly property bool ready: loader.status === RuntimeLoader.Success && extent > 0
    readonly property real fit: ready ? modelSize / extent : 1
    property real appear: 1

    // Pemuatan model besar: RuntimeLoader mem-parsing glTF di thread GUI, jadi selama itu antarmuka
    // pasti berhenti sesaat. Yang bisa kita atur adalah AGAR TIDAK TERLIHAT MEMBEKU: model lama
    // disembunyikan seketika, indikator "Memuat model" ditampilkan, dan source baru baru dipasang
    // setelah jeda singkat supaya indikatornya sempat tergambar sebelum proses berat dimulai.
    property string requestedSource: controller.modelSource
    property string activeSource: ""
    property bool loading: false
    onRequestedSourceChanged: {
        if (requestedSource === "") return
        root.loading = true
        root.extent = 0                       // sembunyikan model lama & buang bounds lamanya
        loadDelay.restart()
    }
    Timer {
        id: loadDelay
        interval: 90                          // beri waktu 1-2 frame untuk menggambar indikator memuat
        onTriggered: {
            root.activeSource = root.requestedSource
            loadWatchdog.restart()
        }
    }
    // Jaring pengaman: kalau setelah sekian lama model belum siap (macet/berkas rusak/kosong),
    // laporkan gagal supaya controller mengembalikan ke model sebelumnya, bukan layar kosong.
    Timer {
        id: loadWatchdog
        interval: 45000
        onTriggered: if (root.loading) root.failLoad("waktu memuat habis")
    }
    function failLoad(reason) {
        loadWatchdog.stop()
        boundsFreeze.stop()
        root.loading = false
        controller.modelStatus(false, reason)
    }

    // Dipicu dari status loader (bukan dari root.ready), karena root.ready sendiri butuh
    // extent > 0, yang baru terisi setelah Timer ini jalan. Kalau dipicu dari root.ready,
    // keduanya saling menunggu dan model tidak pernah dianggap siap/tidak pernah tampil.
    Connections {
        target: loader
        function onStatusChanged() {
            if (loader.status === RuntimeLoader.Success) boundsFreeze.restart()
            else if (loader.status === RuntimeLoader.Error) root.failLoad(loader.errorString)
        }
    }
    // Delay singkat: beri waktu model (dan pose awal animasinya) settle dulu sebelum bounds diukur,
    // supaya ukuran yang dibekukan tidak kebetulan diambil dari frame pose yang aneh/ekstrem.
    Timer {
        id: boundsFreeze
        interval: 60
        onTriggered: {
            var mn = loader.bounds.minimum
            var mx = loader.bounds.maximum
            var ext = Math.max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z)
            if (!isFinite(ext) || ext <= 0) {         // model kosong / bounds tidak valid
                root.failLoad("model kosong atau ukurannya tidak valid")
                return
            }
            root.bMin = mn
            root.bMax = mx
            root.extent = ext
            loadWatchdog.stop()
            root.loading = false
            controller.modelStatus(true, "")
            appearAnim.restart()
        }
    }
    NumberAnimation { id: appearAnim; target: root; property: "appear"; from: 0.6; to: 1; duration: 380; easing.type: Easing.OutCubic }

    Connections {
        target: controller
        function onViewCommand(name, arg) {
            if (name === "rotate") root.rotate(arg)
            else if (name === "spin") { var sp = arg.split(","); root.spin(parseFloat(sp[0]), parseFloat(sp[1])) }
            else if (name === "zoom") root.zoomBy(parseFloat(arg))
            else if (name === "resetZoom") root.zoomGoal = 1
        }
    }

    // Latar, grid, dan model.
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
                // Membantu penyortiran kedalaman untuk geometri opaque yang saling berdempetan
                // (mis. senjata yang menempel rapat ke tubuh model), mengurangi z-fighting.
                depthPrePassEnabled: true
            }

            // Beberapa lampu dari arah berbeda (bukan cuma satu DirectionalLight) supaya bagian
            // model yang tidak menghadap satu sumber cahaya tidak jadi gelap/hitam - penting untuk
            // material metallic/PBR (mis. pesawat) yang jauh lebih gelap daripada model
            // unlit/sederhana kalau cahayanya kurang dari segala arah.
            DirectionalLight { eulerRotation.x: -28; eulerRotation.y: -32; brightness: 1.4; ambientColor: "#606060" }
            DirectionalLight { eulerRotation.x: 35; eulerRotation.y: 150; brightness: 0.9 }
            DirectionalLight { eulerRotation.x: -150; eulerRotation.y: 60; brightness: 0.7 }

            // "Mode 360": modelnya sendiri DIAM di tengah (Node di bawah tidak diberi rotation
            // sama sekali). Yang berputar justru rig kamera ini, mengelilingi model - persis
            // seperti orang berjalan mengelilingi hologram yang diam di tempat. Semua kendali yang
            // sebelumnya memutar model (drag mouse, gesture tangan/spin, tombol rotate, idle-spin)
            // sekarang dipakai untuk mengorbit kamera; posisi/rotasi kamera-nya sama seperti
            // sebelumnya, cuma sekarang jadi anak dari rig yang berputar, bukan model.
            Node {
                id: orbitRig
                rotation: Qt.quaternion(root.currentRot.w, root.currentRot.x, root.currentRot.y, root.currentRot.z)
                Node {
                    eulerRotation.y: root.idleAngle
                    PerspectiveCamera {
                        readonly property real dist: root.baseDistance / root.zoom
                        position: Qt.vector3d(0, -dist * 2 * root.lift * 0.5774, dist)
                        clipNear: 20
                        clipFar: 4000
                    }
                }
            }

            // Model statis: tidak ada rotation di sini sama sekali, jadi tidak lagi ikut berputar.
            Node {
                visible: root.ready
                readonly property real s: root.fit * root.appear
                scale: Qt.vector3d(s, s, s)
                position: Qt.vector3d(-(root.bMin.x + root.bMax.x) / 2 * s,
                                      -(root.bMin.y + root.bMax.y) / 2 * s,
                                      -(root.bMin.z + root.bMax.z) / 2 * s)
                RuntimeLoader {
                    id: loader
                    source: root.activeSource
                }
            }
        }
    }

    // Indikator memuat: tampil selama model baru diproses (terutama model besar), supaya jeda
    // terasa sebagai "sedang memuat", bukan aplikasi yang hang.
    Txt {
        id: loadingLabel
        anchors.centerIn: parent
        visible: root.loading
        text: "MEMUAT MODEL…"
        font.pixelSize: Theme.fsSmall
        font.letterSpacing: Theme.px(1.5)
        color: Theme.text
        SequentialAnimation on opacity {
            running: root.loading
            loops: Animation.Infinite
            NumberAnimation { from: 0.35; to: 1; duration: 600; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 0.35; duration: 600; easing.type: Easing.InOutSine }
        }
    }
}
