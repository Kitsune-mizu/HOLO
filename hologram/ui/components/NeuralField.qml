import QtQuick
import "../theme"

// Latar animasi "jaringan neural" untuk Mode AI (lihat Main.qml). Node-node bergerak pelan dan
// saling terhubung dengan garis; titik terang merambat di sepanjang garis itu sebagai "sinyal".
// Saat `active` true (AI sedang bekerja/menjawab), sinyalnya lebih cepat dan lebih terang -
// idle-nya tetap hidup (tidak diam total) tapi jauh lebih tenang, supaya jelas kelihatan bedanya
// AI "diam" vs "berpikir" tanpa perlu teks status.
Item {
    id: root
    property bool active: false

    // Pengaman: kalau Canvas gagal digambar untuk alasan apapun (driver aneh, dsb.), jangan sampai
    // membanjiri log/CPU - matikan animasinya sendiri dan biarkan latar polos Theme.bg saja.
    property bool broken: false

    // Dipanggil dari luar (Main.qml) saat pesan dikirim / balasan AI datang - animasi pipeline:
    // teks -> biner -> mengalir ke jaringan -> keluar sebagai output. Aman dipanggil kapan saja,
    // termasuk kalau Canvas sedang "broken" (tidak melakukan apa-apa).
    function burstInput() { if (!root.broken) canvas.spawnInput() }
    function burstOutput() { if (!root.broken) canvas.spawnOutput() }

    Rectangle { anchors.fill: parent; color: Theme.bg }

    // Vignette lembut: sedikit lebih gelap ke tepi, menarik fokus ke tengah (tempat chat berada)
    // dan memberi kesan kedalaman dibanding latar polos rata.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0.12) }
            GradientStop { position: 0.5; color: Qt.rgba(0, 0, 0, 0) }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.18) }
        }
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        visible: !root.broken
        renderStrategy: Canvas.Cooperative

        property var nodes: []
        property var edges: []
        property var particles: []     // efek pipeline input/output - lihat spawnInput/spawnOutput
        property real t: 0
        property int builtW: -1
        property int builtH: -1

        function spawnInput() {
            // Teks pengguna "berubah jadi biner" dan mengalir dari tepi kiri ke tengah jaringan -
            // merepresentasikan input yang masuk diproses. Bukan teks aslinya (privasi tidak perlu
            // dijaga di sini karena ini cuma efek visual), cukup karakter 0/1 acak yang cukup untuk
            // kesan "data mengalir".
            var cx = width / 2, cy = height / 2
            for (var i = 0; i < 26; i++) {
                var sy = Math.random() * height
                particles.push({
                    kind: "in", ch: Math.random() < 0.5 ? "0" : "1",
                    x: -10, y: sy, tx: cx + (Math.random() - 0.5) * width * 0.25, ty: cy + (Math.random() - 0.5) * height * 0.25,
                    life: 0, maxLife: 0.9 + Math.random() * 0.5, delay: i * 0.02
                })
            }
        }

        function spawnOutput() {
            // Balasan AI "keluar" sebagai gelombang partikel terang memancar dari tengah -
            // merepresentasikan output yang sudah jadi, melengkapi pipeline input->proses->output.
            var cx = width / 2, cy = height / 2
            for (var i = 0; i < 34; i++) {
                var ang = (i / 34) * Math.PI * 2 + Math.random() * 0.2
                var dist = Math.min(width, height) * (0.35 + Math.random() * 0.25)
                particles.push({
                    kind: "out", ch: Math.random() < 0.5 ? "1" : "0",
                    x: cx, y: cy, tx: cx + Math.cos(ang) * dist, ty: cy + Math.sin(ang) * dist,
                    life: 0, maxLife: 0.7 + Math.random() * 0.4, delay: 0
                })
            }
        }

        property real intensity: 0     // dihaluskan tiap frame menuju (active ? 1 : 0), lihat onPaint

        function rebuild() {
            var w = Math.max(1, width), h = Math.max(1, height)
            builtW = width; builtH = height
            var count = Math.max(18, Math.min(70, Math.round((w * h) / 26000)))
            var ns = []
            for (var i = 0; i < count; i++) {
                // "depth" semu (0.55-1.45): node yang lebih "dekat" digambar lebih besar/terang dan
                // bergerak sedikit lebih cepat - kesan parallax ringan, bukan cuma titik datar.
                var depth = 0.55 + Math.random() * 0.9
                ns.push({
                    x: Math.random() * w, y: Math.random() * h,
                    vx: (Math.random() - 0.5) * 10, vy: (Math.random() - 0.5) * 10,
                    r: (1.3 + Math.random() * 1.6) * depth, depth: depth,
                    twinklePhase: Math.random() * Math.PI * 2
                })
            }
            var es = []
            var maxDist = Math.max(w, h) * 0.22
            for (i = 0; i < ns.length; i++) {
                for (var j = i + 1; j < ns.length; j++) {
                    var dx = ns[i].x - ns[j].x, dy = ns[i].y - ns[j].y
                    var d = Math.sqrt(dx * dx + dy * dy)
                    if (d < maxDist) es.push({ a: i, b: j, d: d, seed: Math.random(), speed: 0.25 + Math.random() * 0.5, flash: 0 })
                }
            }
            nodes = ns
            edges = es
        }

        onWidthChanged: rebuildTimer.restart()
        onHeightChanged: rebuildTimer.restart()
        Timer { id: rebuildTimer; interval: 120; onTriggered: canvas.rebuild() }

        onPaint: {
            try {
                if (builtW !== width || builtH !== height) rebuild()
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                if (nodes.length === 0) return

                // Dihaluskan menuju target, bukan lompat seketika - transisi diam<->berpikir jadi
                // mengalir, bukan "klik" tiba-tiba.
                intensity += ((root.active ? 1 : 0) - intensity) * 0.06
                var speedMul = 1 + intensity * 1.6
                var dt = 1 / 30

                // integrasi posisi node (drift pelan, pantul di tepi) - node "lebih dekat" (depth
                // lebih besar) bergerak sedikit lebih cepat, kesan parallax.
                for (var i = 0; i < nodes.length; i++) {
                    var n = nodes[i]
                    n.x += n.vx * dt * speedMul * 0.35 * n.depth
                    n.y += n.vy * dt * speedMul * 0.35 * n.depth
                    if (n.x < 0 || n.x > width) n.vx *= -1
                    if (n.y < 0 || n.y > height) n.vy *= -1
                    n.x = Math.max(0, Math.min(width, n.x))
                    n.y = Math.max(0, Math.min(height, n.y))
                }

                // garis penghubung, transparansi mengikuti jarak
                ctx.lineWidth = 1
                var maxD = Math.max(width, height) * 0.22
                for (i = 0; i < edges.length; i++) {
                    var e = edges[i]
                    var na = nodes[e.a], nb = nodes[e.b]
                    var dx = na.x - nb.x, dy = na.y - nb.y
                    var d = Math.sqrt(dx * dx + dy * dy)
                    var alpha = Math.max(0, 1 - d / maxD) * (0.22 + intensity * 0.18)
                    // Percikan sinaps acak: sesekali satu garis "menyala" sendiri, independen dari
                    // sinyal berjalan di bawah - kesan jaringan hidup/organik, bukan metronom.
                    if (e.flash > 0) {
                        alpha += e.flash * 0.6
                        e.flash -= dt * 1.8
                    } else if (Math.random() < 0.0022 * (1 + intensity * 2)) {
                        e.flash = 1
                    }
                    if (alpha <= 0.005) continue
                    ctx.strokeStyle = Qt.rgba(1, 1, 0.784, Math.min(1, alpha))
                    ctx.beginPath()
                    ctx.moveTo(na.x, na.y)
                    ctx.lineTo(nb.x, nb.y)
                    ctx.stroke()
                }

                // sinyal terang merambat di sepanjang sebagian garis
                t += dt * speedMul
                for (i = 0; i < edges.length; i++) {
                    e = edges[i]
                    var frac = (t * e.speed + e.seed) % 1
                    na = nodes[e.a]; nb = nodes[e.b]
                    var px = na.x + (nb.x - na.x) * frac
                    var py = na.y + (nb.y - na.y) * frac
                    var glow = 0.35 + intensity * 0.6
                    ctx.beginPath()
                    ctx.fillStyle = Qt.rgba(1, 1, 0.784, glow)
                    ctx.arc(px, py, 1.3 + intensity * 1.1, 0, Math.PI * 2)
                    ctx.fill()
                }

                // node itu sendiri: halo lembut (glow) + inti padat, dengan kedip pelan per-node
                // supaya jaringan terasa "bernapas" bahkan saat idle.
                for (i = 0; i < nodes.length; i++) {
                    n = nodes[i]
                    var twinkle = 0.75 + 0.25 * Math.sin(t * 1.4 + n.twinklePhase)
                    var haloR = n.r * (3 + intensity * 2)
                    var grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, haloR)
                    grad.addColorStop(0, Qt.rgba(1, 1, 0.784, 0.22 * twinkle * (0.6 + intensity * 0.6)))
                    grad.addColorStop(1, Qt.rgba(1, 1, 0.784, 0))
                    ctx.beginPath()
                    ctx.fillStyle = grad
                    ctx.arc(n.x, n.y, haloR, 0, Math.PI * 2)
                    ctx.fill()

                    ctx.beginPath()
                    ctx.fillStyle = Qt.rgba(0.96, 0.96, 0.86, (0.45 + intensity * 0.25) * twinkle)
                    ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2)
                    ctx.fill()
                }

                // partikel pipeline input/output (lihat spawnInput/spawnOutput)
                if (particles.length > 0) {
                    ctx.font = "11px monospace"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    var alive = []
                    for (i = 0; i < particles.length; i++) {
                        var p = particles[i]
                        if (p.delay > 0) { p.delay -= dt; alive.push(p); continue }
                        p.life += dt
                        var frac = Math.min(1, p.life / p.maxLife)
                        var ease = 1 - Math.pow(1 - frac, 3)          // ease-out: cepat lalu melambat
                        var px2 = p.x + (p.tx - p.x) * ease
                        var py2 = p.y + (p.ty - p.y) * ease
                        var a = p.kind === "in" ? Math.min(1, frac * 3) * (1 - frac) * 2.2 : (1 - frac)
                        a = Math.max(0, Math.min(1, a))
                        if (a > 0.01) {
                            ctx.fillStyle = Qt.rgba(1, 1, 0.784, a)
                            ctx.fillText(p.ch, px2, py2)
                        }
                        if (frac < 1) alive.push(p)
                    }
                    particles = alive
                }
            } catch (err) {
                console.warn("NeuralField: gagal menggambar, animasi dimatikan -", err)
                root.broken = true
            }
        }

        Timer {
            interval: 33   // ~30fps - cukup halus, tidak membebani GPU/CPU untuk sekadar latar
            running: canvas.visible
            repeat: true
            onTriggered: canvas.requestPaint()
        }
    }
}
