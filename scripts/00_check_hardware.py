"""カメラとプロジェクタが撮影可能な状態かを確認する。

    uv run --no-sync python scripts/00_check_hardware.py

本番の撮影に入る前の動作確認用です。設定どおりにカメラを開いて 1 枚撮影し、
プロジェクタに全白・全黒・グレイコードパターンを順に表示します。

    --camera-only     プロジェクタを使わずカメラだけ確認する
    --projector-only  カメラを使わずプロジェクタだけ確認する
"""

from __future__ import annotations

import argparse
import sys
import time

from slr import cli
from slr.config import Config


def check_camera(config: Config) -> None:
    from slr.camera import Camera

    print("--- カメラ ---")
    with Camera(config) as camera:
        camera.start()
        frame = camera.grab()
        camera.stop()
    print(f"  撮影テスト  : {frame.shape[1]} x {frame.shape[0]} {frame.dtype}")
    print(f"  輝度        : 最小 {frame.min()} / 平均 {frame.mean():.1f} / 最大 {frame.max()}")
    print("  OK")


def check_projector(config: Config, seconds: float) -> None:
    from slr import patterns
    from slr.projector import Projector

    print("--- プロジェクタ ---")
    names, paths = patterns.load(config)
    by_name = dict(zip(names, paths, strict=True))
    sequence = [
        name
        for name in (patterns.WHITE_NAME, patterns.BLACK_NAME, "pattern_00", "pattern_20")
        if name in by_name
    ]

    with Projector(config) as projector:
        x, y = projector.position
        print(f"  表示位置    : ({x}, {y})")
        print(f"  投影解像度  : {config.projector.width} x {config.projector.height}")
        for name in sequence:
            print(f"  表示中      : {name}")
            projector.show(by_name[name])
            time.sleep(seconds)
            if projector.aborted:
                print("  Esc で中断しました。")
                return
    print("  OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument("--camera-only", action="store_true")
    parser.add_argument("--projector-only", action="store_true")
    parser.add_argument(
        "--seconds", type=float, default=1.5, help="各パターンの表示秒数"
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    print(f"設定: {config.source}\n")

    if not args.projector_only:
        check_camera(config)
        print()
    if not args.camera_only:
        check_projector(config, args.seconds)

    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
