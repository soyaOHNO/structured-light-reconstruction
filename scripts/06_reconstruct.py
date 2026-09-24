"""デコード結果とキャリブレーションから三次元点群を復元する。

    uv run --no-sync python scripts/06_reconstruct.py <実験名> --calibration <校正名>

data/results/<実験名>/ のデコード結果と data/results/<校正名>/calibration.json を
使い、同じ場所に点群を書き出します。

    points.ply      点群（CloudCompare や MeshLab で開けます）
    points.npy      同じ点群の numpy 配列（mm 単位、カメラ原点）
    depth.png       奥行きを色で表した確認用画像
    reconstruct.json  点数・奥行き範囲・再投影誤差

キャリブレーションを撮ったときからカメラとプロジェクタを動かしていると、
結果は意味を持ちません。
"""

from __future__ import annotations

import argparse
import sys

import cv2

from slr import calibration as calib
from slr import cli, decode, reconstruct
from slr.config import Config
from slr.patterns import WHITE_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="実験名（data/raw/ 以下のディレクトリ名）")
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument(
        "--calibration",
        required=True,
        help="キャリブレーション結果のある実験名",
    )
    parser.add_argument("--no-color", action="store_true", help="色を付けない")
    args = parser.parse_args()

    config = Config.load(args.config)
    calibration_path = config.result_dir(args.calibration) / "calibration.json"
    calibration = calib.load(calibration_path)

    print(f"設定       : {config.source}")
    print(f"校正       : {calibration_path}")
    print(f"  再投影誤差: カメラ {calibration.camera_error:.3f}"
          f" / プロジェクタ {calibration.projector_error:.3f} 画素")
    print(f"  基線長    : {calibration.baseline_mm:.0f} mm")
    print(f"入力       : {config.raw_dir(args.name)}")

    decoded = decode.decode_capture(config, args.name)
    height, width = decoded.shape
    print(f"有効画素   : {int(decoded.mask.sum()):,} / {width * height:,}"
          f"（{decoded.valid_ratio * 100:.1f}%）")

    if (width, height) != calibration.camera_size:
        raise ValueError(
            f"撮影画像 {width}x{height} が校正時の "
            f"{calibration.camera_size[0]}x{calibration.camera_size[1]} と違います"
        )

    color_image = None
    if not args.no_color:
        white_path = config.raw_dir(args.name) / f"{WHITE_NAME}.png"
        color_image = cv2.imread(str(white_path), cv2.IMREAD_UNCHANGED)

    cloud = reconstruct.triangulate(
        decoded,
        calibration,
        min_depth_mm=config.reconstruct.min_depth_mm,
        max_depth_mm=config.reconstruct.max_depth_mm,
        max_error_px=config.reconstruct.max_reprojection_error_px,
        color_image=color_image,
    )

    kept = len(cloud)
    total = int(decoded.mask.sum())
    print()
    print(f"三次元点   : {kept:,} 点（有効画素の {kept / total * 100:.1f}%）")
    if kept == 0:
        raise RuntimeError(
            "条件を満たす点がありませんでした。config の [reconstruct] の"
            "奥行き範囲と再投影誤差の上限を確認してください。"
        )

    near, far = cloud.depth_range
    print(f"奥行き     : {near:.0f} - {far:.0f} mm")
    print(f"再投影誤差 : 中央値 {float(cloud.errors.mean()):.3f} 画素")

    output_dir = config.result_dir(args.name)
    ply_path = reconstruct.save(cloud, output_dir, source=str(config.raw_dir(args.name)))
    cv2.imwrite(
        str(output_dir / "depth.png"), reconstruct.depth_preview(cloud, decoded.shape)
    )

    print()
    print(f"保存先: {ply_path}")
    print(f"        {output_dir / 'depth.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
