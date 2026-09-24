"""パターンを投影しながら自動で撮影し、data/raw/<実験名>/ に保存する。

    uv run --no-sync python scripts/02_capture.py <実験名>

投影 → 待機 → 撮影 を全パターン分繰り返します。撮影画像はパターンと同じ
ファイル名で保存するので、デコード時に名前で対応づけられます。

実行前に SpinView を終了してください。カメラは同時に 1 つのアプリからしか
開けません。撮影中は Esc で中断できます。
"""

from __future__ import annotations

import argparse
import sys

from slr import capture, cli, patterns
from slr.camera import Camera
from slr.config import Config
from slr.projector import Projector


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="実験名（保存先ディレクトリ名になります）")
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument("--yes", action="store_true", help="開始前の確認を省略する")
    args = parser.parse_args()

    config = Config.load(args.config)
    output_dir = config.raw_dir(args.name)

    # 既存の撮影データには追記しません。異なる条件の画像が混ざると、
    # 後からどれがどれか分からなくなるためです。
    if output_dir.exists() and any(output_dir.iterdir()):
        print(f"すでにデータがあります: {output_dir}")
        print("別の実験名を指定してください。")
        return 1

    names, pattern_paths = patterns.load(config)
    estimate = len(names) * (
        config.capture.warmup_sec + config.camera.exposure_time_us / 1.0e6
    )

    print(f"設定       : {config.source}")
    print(f"パターン   : {config.pattern_dir}（{len(names)} 枚）")
    print(f"保存先     : {output_dir}")
    print(f"所要時間   : 約 {estimate:.0f} 秒")
    print()

    if not args.yes:
        print("プロジェクタとカメラの準備ができたら Enter を押してください。")
        print("（SpinView は終了しておくこと。撮影中は Esc で中断できます）")
        input()

    with Camera(config) as camera, Projector(config) as projector:
        camera.start()
        print()
        elapsed = capture.capture_sequence(
            config,
            camera,
            projector,
            names,
            pattern_paths,
            output_dir,
            on_saved=capture.print_progress,
        )
        camera.stop()
        capture.save_metadata(output_dir, config, camera, names, elapsed)

    print()
    print(f"完了: {len(names)} 枚を {elapsed:.1f} 秒で撮影しました。")
    print(f"保存先: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
