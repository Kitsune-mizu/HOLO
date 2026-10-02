pragma Singleton
import QtQuick

// Semua warna, radius, jarak, dan ukuran ada di sini. Palet diambil dari gambar referensi.
QtObject {
    // Ukuran jendela diisi dari Main.qml. `u` = skala: 1.0 pada 1280x720.
    property real viewportW: 1280
    property real viewportH: 720
    readonly property real u: Math.max(0.55, Math.min(2.6, Math.min(viewportH / 720, viewportW / 960)))
    function px(n) { return n * u }

    // Warna
    readonly property color bg: "#201e1b"
    readonly property color grid: "#282622"
    readonly property color ink: "#ffffc8"          // garis wireframe, judul
    readonly property color text: "#f5f5dc"
    readonly property color muted: "#a5a582"        // border kamera, teks sekunder
    readonly property color dim: "#757459"          // teks info kecil
    readonly property color contrast: "#201e1b"        // teks di atas latar krem
    readonly property color warn: "#e8b378"
    readonly property color card: Qt.rgba(0.075, 0.07, 0.06, 0.80)
    readonly property color cardSolid: "#191815"
    readonly property color line: Qt.rgba(0.647, 0.647, 0.51, 0.45)
    readonly property color tint: Qt.rgba(1, 1, 0.78, 0.08)
    readonly property color tintStrong: Qt.rgba(1, 1, 0.78, 0.16)

    // Bentuk
    readonly property real radius: px(16)
    readonly property real radiusSmall: px(10)
    readonly property real gap: px(8)
    readonly property real margin: px(24)

    // Teks
    // Font monospace pertama yang terpasang di sistem, urut dari yang paling enak dibaca.
    readonly property string fontFamily: {
        var wanted = ["Cascadia Mono", "Consolas", "SF Mono", "Menlo", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"]
        var have = Qt.fontFamilies()
        for (var i = 0; i < wanted.length; i++)
            if (have.indexOf(wanted[i]) >= 0) return wanted[i]
        return "monospace"
    }
    readonly property real fsTitle: px(30)
    readonly property real fsLabel: px(20)
    readonly property real fsBody: px(13)
    readonly property real fsSmall: px(11.5)

    // Gerak
    readonly property int fast: 160
    readonly property int normal: 320
    readonly property int slow: 420
}
