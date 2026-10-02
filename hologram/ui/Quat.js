.pragma library
// Rotasi model dengan quaternion. Swipe selalu memutar terhadap sumbu layar
// (vertikal untuk kanan/kiri, horizontal untuk atas/bawah), berapa pun posisi model sekarang.

function make(w, x, y, z) { return { w: w, x: x, y: y, z: z } }

function axisAngle(ax, ay, az, deg) {
    var h = deg * Math.PI / 360
    var s = Math.sin(h)
    return make(Math.cos(h), ax * s, ay * s, az * s)
}

// Hasil kali Hamilton: terapkan b dulu, lalu a.
function mul(a, b) {
    return make(
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w)
}

function normalize(q) {
    var n = Math.sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z) || 1
    return make(q.w / n, q.x / n, q.y / n, q.z / n)
}

function slerp(a, b, t) {
    var d = a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z
    var bw = b.w, bx = b.x, by = b.y, bz = b.z
    if (d < 0) { d = -d; bw = -bw; bx = -bx; by = -by; bz = -bz }
    if (d > 0.9995) {
        return normalize(make(a.w + (bw - a.w) * t, a.x + (bx - a.x) * t, a.y + (by - a.y) * t, a.z + (bz - a.z) * t))
    }
    var th = Math.acos(d)
    var s = Math.sin(th)
    var wa = Math.sin((1 - t) * th) / s
    var wb = Math.sin(t * th) / s
    return make(a.w * wa + bw * wb, a.x * wa + bx * wb, a.y * wa + by * wb, a.z * wa + bz * wb)
}

// Putaran satu langkah. Kanan: bagian depan model bergerak ke kanan. Bawah: bagian depan turun.
function step(direction, deg) {
    if (direction === "right") return axisAngle(0, 1, 0, deg)
    if (direction === "left") return axisAngle(0, 1, 0, -deg)
    if (direction === "down") return axisAngle(1, 0, 0, deg)
    if (direction === "up") return axisAngle(1, 0, 0, -deg)
    return make(1, 0, 0, 0)
}

// Posisi awal: agak miring supaya terlihat tiga dimensi.
function start() { return mul(axisAngle(1, 0, 0, 18), axisAngle(0, 1, 0, -32)) }
