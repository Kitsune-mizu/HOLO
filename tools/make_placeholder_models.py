"""Membuat model 3D sederhana (.glb) di assets/models/ kalau belum punya model asli.

Tanpa dependensi luar: file glTF Biner ditulis langsung dengan struct.
Bentuknya generik (bukan replika pesawat tertentu). Hidung menghadap +X, atas +Y.

    python tools/make_placeholder_models.py
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "models"

Vec = tuple[float, float, float]
Tri = tuple[Vec, Vec, Vec]


# ---------------------------------------------------------------- vektor kecil
def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normal(t: Tri) -> Vec:
    n = _cross(_sub(t[1], t[0]), _sub(t[2], t[0]))
    length = math.sqrt(_dot(n, n))
    return (0.0, 1.0, 0.0) if length < 1e-12 else (n[0] / length, n[1] / length, n[2] / length)


def _area2(t: Tri) -> float:
    n = _cross(_sub(t[1], t[0]), _sub(t[2], t[0]))
    return math.sqrt(_dot(n, n))


def _outward(tris: list[Tri]) -> list[Tri]:
    """Balik sisi segitiga yang menghadap ke dalam (untuk bentuk cembung)."""
    pts = [p for t in tris for p in t]
    c = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
    out: list[Tri] = []
    for t in tris:
        if _area2(t) < 1e-9:
            continue
        mid = tuple(sum(v[i] for v in t) / 3 for i in range(3))
        if _dot(_normal(t), _sub(mid, c)) < 0:
            t = (t[0], t[2], t[1])
        out.append(t)
    return out


# ---------------------------------------------------------------- bentuk dasar
def convex(points_rings: list[list[Vec]], cap_start: bool = True, cap_end: bool = True) -> list[Tri]:
    """Sambung dua atau lebih cincin titik (jumlah sama) menjadi permukaan tertutup."""
    tris: list[Tri] = []
    for a, b in zip(points_rings, points_rings[1:]):
        n = len(a)
        for i in range(n):
            j = (i + 1) % n
            tris.append((a[i], a[j], b[j]))
            tris.append((a[i], b[j], b[i]))
    for ring, wanted in ((points_rings[0], cap_start), (points_rings[-1], cap_end)):
        if wanted:
            tris += [(ring[0], ring[i], ring[i + 1]) for i in range(1, len(ring) - 1)]
    return _outward(tris)


def box(cx: float, cy: float, cz: float, sx: float, sy: float, sz: float) -> list[Tri]:
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    ring0 = [(cx - hx, cy - hy, cz - hz), (cx - hx, cy - hy, cz + hz), (cx - hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz - hz)]
    ring1 = [(cx + hx, y, z) for _, y, z in ring0]
    return convex([ring0, ring1])


def tube_x(x0: float, x1: float, r0: tuple[float, float], r1: tuple[float, float],
           y: float = 0.0, z: float = 0.0, n: int = 8) -> list[Tri]:
    """Tabung/kerucut sepanjang X. r = (radius_y, radius_z)."""
    def ring(x: float, r: tuple[float, float]) -> list[Vec]:
        return [(x, y + r[0] * math.sin(2 * math.pi * k / n), z + r[1] * math.cos(2 * math.pi * k / n)) for k in range(n)]
    return convex([ring(x0, r0), ring(x1, r1)])


def disc_y(cx: float, cy: float, cz: float, radius: float, thick: float, n: int = 12) -> list[Tri]:
    def ring(y: float) -> list[Vec]:
        return [(cx + radius * math.cos(2 * math.pi * k / n), y, cz + radius * math.sin(2 * math.pi * k / n)) for k in range(n)]
    return convex([ring(cy - thick / 2), ring(cy + thick / 2)])


def flat_xz(poly: list[tuple[float, float]], y: float, thick: float) -> list[Tri]:
    """Poligon cembung di bidang XZ (titik = (x, z)), ditebalkan searah Y."""
    return convex([[(x, y - thick / 2, z) for x, z in poly], [(x, y + thick / 2, z) for x, z in poly]])


def flat_xy(poly: list[tuple[float, float]], z: float, thick: float) -> list[Tri]:
    """Poligon cembung di bidang XY (titik = (x, y)), ditebalkan searah Z."""
    return convex([[(x, y, z - thick / 2) for x, y in poly], [(x, y, z + thick / 2) for x, y in poly]])


def mirror_z(tris: list[Tri]) -> list[Tri]:
    return [tuple((x, y, -z) for x, y, z in t) for t in tris]  # type: ignore[misc]


def rot_y(tris: list[Tri], deg: float) -> list[Tri]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [tuple((x * c + z * s, y, -x * s + z * c) for x, y, z in t) for t in tris]  # type: ignore[misc]


def move(tris: list[Tri], dx: float = 0, dy: float = 0, dz: float = 0) -> list[Tri]:
    return [tuple((x + dx, y + dy, z + dz) for x, y, z in t) for t in tris]  # type: ignore[misc]


# ---------------------------------------------------------------- model
def pyramid() -> list[Tri]:
    h = 0.5
    base = [(-0.5, -h, -0.5), (-0.5, -h, 0.5), (0.5, -h, 0.5), (0.5, -h, -0.5)]
    apex = (0.0, h, 0.0)
    tris = [(base[i], base[(i + 1) % 4], apex) for i in range(4)]
    tris += [(base[0], base[2], base[1]), (base[0], base[3], base[2])]
    return _outward(tris)


def drone() -> list[Tri]:
    t: list[Tri] = box(0, 0, 0, 0.30, 0.09, 0.30)
    t += box(0, 0.06, 0, 0.16, 0.03, 0.16)
    for angle in (45, -45):
        t += rot_y(box(0, 0.0, 0, 0.90, 0.03, 0.045), angle)
    for sx in (-1, 1):
        for sz in (-1, 1):
            mx, mz = sx * 0.318, sz * 0.318
            t += tube_x(mx - 0.03, mx + 0.03, (0.04, 0.04), (0.04, 0.04), y=0.04, z=mz, n=6)
            t += disc_y(mx, 0.085, mz, 0.19, 0.008)
    t += box(0.17, -0.075, 0, 0.07, 0.06, 0.07)
    for sz in (-1, 1):
        t += box(0, -0.15, sz * 0.13, 0.36, 0.015, 0.015)
        for sx in (-1, 1):
            t += box(sx * 0.13, -0.11, sz * 0.13, 0.015, 0.09, 0.015)
    return t


def fighter() -> list[Tri]:
    t: list[Tri] = tube_x(0.50, 0.26, (0.004, 0.004), (0.045, 0.06), n=6)
    t += tube_x(0.26, -0.30, (0.045, 0.06), (0.05, 0.07), n=6)
    t += tube_x(-0.30, -0.47, (0.05, 0.07), (0.04, 0.05), n=6)
    t += tube_x(-0.47, -0.53, (0.04, 0.05), (0.03, 0.035), n=6)
    t += tube_x(0.30, 0.02, (0.006, 0.006), (0.05, 0.04), y=0.055, n=6)
    wing = flat_xz([(0.16, 0.05), (-0.26, 0.44), (-0.34, 0.44), (-0.34, 0.05)], -0.005, 0.012)
    t += wing + mirror_z(wing)
    stab = flat_xz([(-0.30, 0.05), (-0.46, 0.20), (-0.52, 0.20), (-0.52, 0.05)], -0.005, 0.010)
    t += stab + mirror_z(stab)
    t += flat_xy([(-0.16, 0.05), (-0.40, 0.30), (-0.50, 0.30), (-0.50, 0.05)], 0.0, 0.012)
    return t


def bomber() -> list[Tri]:
    t: list[Tri] = tube_x(0.52, 0.36, (0.01, 0.01), (0.07, 0.07), n=8)
    t += tube_x(0.36, -0.20, (0.07, 0.07), (0.07, 0.07), n=8)
    t += tube_x(-0.20, -0.52, (0.07, 0.07), (0.02, 0.02), n=8)
    wing = flat_xz([(0.10, 0.05), (-0.12, 0.52), (-0.24, 0.52), (-0.20, 0.05)], 0.0, 0.02)
    t += wing + mirror_z(wing)
    for z in (-0.30, -0.16, 0.16, 0.30):
        t += tube_x(-0.02, 0.16, (0.035, 0.035), (0.035, 0.035), y=-0.045, z=z, n=6)
    stab = flat_xz([(-0.38, 0.03), (-0.50, 0.24), (-0.56, 0.24), (-0.50, 0.03)], 0.02, 0.012)
    t += stab + mirror_z(stab)
    t += flat_xy([(-0.26, 0.06), (-0.46, 0.30), (-0.56, 0.30), (-0.52, 0.06)], 0.0, 0.014)
    return t


MODELS = {"pyramid": pyramid, "drone": drone, "fighter": fighter, "bomber": bomber}


# ---------------------------------------------------------------- penulis GLB
def build_glb(tris: list[Tri], name: str) -> bytes:
    positions = [v for t in tris for v in t]
    normals = [_normal(t) for t in tris for _ in range(3)]
    n = len(positions)
    pos_bin = b"".join(struct.pack("<3f", *p) for p in positions)
    nor_bin = b"".join(struct.pack("<3f", *p) for p in normals)
    idx_bin = struct.pack(f"<{n}I", *range(n))
    blob = pos_bin + nor_bin + idx_bin
    lo = [min(p[i] for p in positions) for i in range(3)]
    hi = [max(p[i] for p in positions) for i in range(3)]
    doc = {
        "asset": {"version": "2.0", "generator": "hologramos/make_placeholder_models.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}]}],
        "materials": [{
            "name": "holo",
            "doubleSided": True,
            "emissiveFactor": [0.55, 0.55, 0.42],
            "pbrMetallicRoughness": {"baseColorFactor": [1.0, 1.0, 0.78, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.9},
        }],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": n, "type": "VEC3", "min": lo, "max": hi},
            {"bufferView": 1, "componentType": 5126, "count": n, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5125, "count": n, "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bin), "target": 34962},
            {"buffer": 0, "byteOffset": len(pos_bin), "byteLength": len(nor_bin), "target": 34962},
            {"buffer": 0, "byteOffset": len(pos_bin) + len(nor_bin), "byteLength": len(idx_bin), "target": 34963},
        ],
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob += b"\x00" * (-len(blob) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(js), b"JSON") + js
        + struct.pack("<I4s", len(blob), b"BIN\x00") + blob
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in MODELS.items():
        data = build_glb(make(), name)
        (OUT / f"{name}.glb").write_bytes(data)
        print(f"{name}.glb  {len(data) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
