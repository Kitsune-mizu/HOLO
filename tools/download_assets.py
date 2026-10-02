"""Mengunduh aset yang tidak ikut di proyek:

  1. Model tangan MediaPipe (hand_landmarker.task, sekitar 7,5 MB) ke assets/ai/
  2. Model Whisper untuk suara ke teks (base sekitar 145 MB) ke assets/whisper/<ukuran>/

    python tools/download_assets.py                 # keduanya, Whisper base
    python tools/download_assets.py --whisper small # Whisper lebih akurat, lebih berat
    python tools/download_assets.py --no-whisper    # hanya model tangan
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HAND_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
HAND_PATH = ROOT / "assets" / "ai" / "hand_landmarker.task"
WHISPER_DIR = ROOT / "assets" / "whisper"


def download_hand_model(force: bool = False) -> bool:
    if HAND_PATH.exists() and HAND_PATH.stat().st_size > 1_000_000 and not force:
        print(f"[tangan] sudah ada: {HAND_PATH.relative_to(ROOT)}")
        return True
    HAND_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HAND_PATH.with_suffix(".part")
    print(f"[tangan] mengunduh {HAND_URL}")
    try:
        with urllib.request.urlopen(HAND_URL, timeout=60) as resp, tmp.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(1 << 16):
                out.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r[tangan] {done / 1e6:5.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        print()
    except (urllib.error.URLError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        print(f"[tangan] GAGAL: {exc}\n         Unduh manual dari alamat di atas lalu simpan sebagai {HAND_PATH.relative_to(ROOT)}")
        return False
    if tmp.stat().st_size < 1_000_000:
        tmp.unlink(missing_ok=True)
        print("[tangan] GAGAL: file yang diterima terlalu kecil.")
        return False
    tmp.replace(HAND_PATH)
    print(f"[tangan] tersimpan: {HAND_PATH.relative_to(ROOT)}")
    return True


def download_whisper(size: str) -> bool:
    target = WHISPER_DIR / size
    if target.is_dir() and (target / "model.bin").exists():
        print(f"[whisper] sudah ada: {target.relative_to(ROOT)}")
        return True
    try:
        from faster_whisper import download_model
    except ImportError:
        print("[whisper] faster-whisper belum terpasang. Jalankan: pip install -r requirements.txt")
        return False
    target.mkdir(parents=True, exist_ok=True)
    print(f"[whisper] mengunduh model '{size}' ke {target.relative_to(ROOT)} (bisa beberapa menit)")
    try:
        download_model(size, output_dir=str(target))
    except Exception as exc:
        print(f"[whisper] GAGAL: {exc}")
        return False
    print("[whisper] selesai.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--whisper", default="base", choices=["tiny", "base", "small", "medium"], help="ukuran model Whisper")
    parser.add_argument("--no-whisper", action="store_true", help="lewati Whisper")
    parser.add_argument("--no-hand", action="store_true", help="lewati model tangan")
    parser.add_argument("--force", action="store_true", help="unduh ulang model tangan")
    args = parser.parse_args()
    ok = True
    if not args.no_hand:
        ok &= download_hand_model(args.force)
    if not args.no_whisper:
        ok &= download_whisper(args.whisper)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
