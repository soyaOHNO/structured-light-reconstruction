"""撮影したグレイコード画像をデコードし、プロジェクタ座標マップを作る。

    uv run --no-sync python scripts/03_decode.py <実験名>

data/raw/<実験名>/ の画像を読み、data/results/<実験名>/ に結果を出します。

    proj_x.npy / proj_y.npy   カメラ画素ごとのプロジェクタ座標（無効画素は -1）
    mask.png                  有効画素
    shadow_mask.png           全白・全黒の差から作った影のマスク
    preview_x.png / preview_y.png   目視確認用のカラー画像

preview は滑らかなグラデーションになっていれば正しく復号できています。まだら
模様やノイズが目立つ場合は、露光や config の [decode] しきい値を見直します。
"""

from __future__ import annotations

import argparse
import sys

from slr import cli, decode
from slr.config import Config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="実験名（data/raw/ 以下のディレクトリ名）")
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument("--force", action="store_true", help="既存の結果を上書きする")
    parser.add_argument(
        "--bits",
        action="store_true",
        help="ビットごとの通過率を表示する（skip_fine_bits を決めるための診断）",
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    source_dir = config.raw_dir(args.name)
    output_dir = config.result_dir(args.name)

    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        print(f"すでに結果があります: {output_dir}")
        print("上書きするには --force を付けてください。")
        return 1

    print(f"設定       : {config.source}")
    print(f"入力       : {source_dir}")
    print(f"使わないビット: {config.decode.skip_fine_bits}（最も細かい側から）")

    if args.bits:
        print()
        print("ビットごとの通過率（影マスク内）:")
        print("  縞幅(投影画素)  通過率")
        for _, stripe, ratio in decode.bit_reliability(config, args.name):
            bar = "#" * int(ratio * 40)
            print(f"  {stripe:10d}   {ratio * 100:5.1f}%  {bar}")
        print()

    result = decode.decode_capture(config, args.name)

    height, width = result.shape
    print(f"カメラ解像度: {width} x {height}")
    print(
        f"有効画素   : {int(result.mask.sum()):,} / {width * height:,}"
        f"（{result.valid_ratio * 100:.1f}%）"
    )

    if result.valid_ratio < 0.01:
        print()
        print("  [警告] 有効画素がほとんどありません。次を確認してください。")
        print("         - 投影範囲とカメラの撮影範囲が重なっているか")
        print("         - 露光が適切か（飽和・露光不足でないか）")
        print("         - config の [decode] しきい値が厳しすぎないか")

    decode.save(result, output_dir, source=str(source_dir))
    print(f"保存先     : {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
