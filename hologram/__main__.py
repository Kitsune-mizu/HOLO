"""Titik masuk: python -m hologram"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="hologram", description="Hologram OS: penampil model 3D dengan AI, gesture, dan suara.")
    parser.add_argument("--no-camera", action="store_true", help="jalan tanpa kamera dan deteksi tangan")
    parser.add_argument("--no-voice", action="store_true", help="jalan tanpa mikrofon dan suara AI")
    parser.add_argument("--config", type=Path, help="path config.toml lain")
    args = parser.parse_args()

    from .app import run

    return run(no_camera=args.no_camera, no_voice=args.no_voice, config_path=args.config)


if __name__ == "__main__":
    sys.exit(main())
