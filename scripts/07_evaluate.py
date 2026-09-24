"""復元した点群の精度を、既知形状との比較で評価する。

    uv run --no-sync python scripts/07_evaluate.py <実験名> --shape plane
    uv run --no-sync python scripts/07_evaluate.py <実験名> --shape sphere --diameter 50

平らな板や球など、形の分かっているものを計測した点群に対して実行します。
その形からのずれが、そのまま計測精度です。

評価する範囲は --roi で画面上の矩形として指定できます。depth.png を見ながら
対象の写っている位置を読み取ってください。省略すると点群全体を使います。

    --roi 400,300,600,500      x=400, y=300, 幅 600, 高さ 500 の範囲

結果は data/results/<実験名>/evaluation_<形状>.json と、残差を色で表した
residual_<形状>.png に保存されます。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import cv2
import numpy as np

from slr import cli, evaluate
from slr.config import Config


def parse_roi(text: str | None) -> tuple[int, int, int, int] | None:
    if text is None:
        return None
    parts = text.replace(" ", "").split(",")
    if len(parts) != 4:
        raise ValueError(f"--roi は x,y,幅,高さ の 4 つで指定します（{text}）")
    return tuple(int(value) for value in parts)  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="実験名（data/results/ 以下のディレクトリ名）")
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument(
        "--shape",
        choices=["plane", "sphere"],
        default="plane",
        help="当てはめる形状",
    )
    parser.add_argument(
        "--diameter",
        type=float,
        default=None,
        help="球の直径の実測値（mm）。指定すると推定値との差を表示する",
    )
    parser.add_argument("--roi", default=None, help="評価する範囲 x,y,幅,高さ")
    parser.add_argument(
        "--threshold",
        type=float,
        default=2.0,
        help="外れ値とみなす、形状からのずれ（mm）",
    )
    parser.add_argument(
        "--note", default=None, help="この評価の条件を記録するメモ（距離や角度など）"
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    result_dir = config.result_dir(args.name)
    points_path = result_dir / "points.npy"
    pixels_path = result_dir / "pixels.npy"

    if not points_path.is_file():
        raise FileNotFoundError(
            f"点群がありません: {points_path}"
            "（先に scripts/06_reconstruct.py を実行してください）"
        )
    points = np.load(points_path).astype(np.float64)
    pixels = np.load(pixels_path) if pixels_path.is_file() else None

    print(f"入力       : {points_path}")
    print(f"点数       : {len(points):,}")

    roi = parse_roi(args.roi)
    if roi is not None:
        if pixels is None:
            raise FileNotFoundError(
                f"{pixels_path} がないため --roi を使えません。"
                "点群を作り直してください。"
            )
        selected = evaluate.select_roi(points, pixels, roi)
        if selected.sum() < 10:
            raise ValueError(
                f"指定した範囲に点が {int(selected.sum())} 個しかありません"
            )
        points, pixels = points[selected], pixels[selected]
        print(f"範囲       : x={roi[0]} y={roi[1]} 幅={roi[2]} 高さ={roi[3]}"
              f" -> {len(points):,} 点")

    if args.shape == "plane":
        fit = evaluate.fit_plane(points, threshold_mm=args.threshold)
    else:
        fit = evaluate.fit_sphere(points, threshold_mm=args.threshold)

    print()
    print(f"当てはめ   : {args.shape}")
    for key, value in fit.parameters.items():
        if isinstance(value, list):
            value = "[" + ", ".join(f"{v:.3f}" for v in value) + "]"
        print(f"  {key:14s}: {value}")

    print()
    print("形状からのずれ（内点のみ）:")
    print(f"  RMS         : {fit.rms:.3f} mm")
    print(f"  平均絶対誤差: {fit.mean_absolute:.3f} mm")
    print(f"  最大         : {fit.max_absolute:.3f} mm")
    print(f"  内点の割合   : {fit.inlier_ratio * 100:.1f}%"
          f"（{int(fit.inliers.sum()):,} / {len(points):,} 点）")

    if args.shape == "sphere" and args.diameter is not None:
        estimated = fit.parameters["radius_mm"] * 2.0
        error = estimated - args.diameter
        print()
        print("直径の比較:")
        print(f"  実測値 {args.diameter:.2f} mm / 推定値 {estimated:.2f} mm")
        print(f"  差 {error:+.3f} mm（{error / args.diameter * 100:+.2f}%）")
        print("  この差はスケールの系統誤差です。"
              "チェッカーボードの square_size_mm を確認してください。")

    payload = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(points_path),
        "shape": args.shape,
        "note": args.note,
        "roi": list(roi) if roi else None,
        "threshold_mm": args.threshold,
        "point_count": len(points),
        "inlier_count": int(fit.inliers.sum()),
        "inlier_ratio": round(fit.inlier_ratio, 4),
        "parameters": fit.parameters,
        "deviation_mm": {
            "rms": round(fit.rms, 4),
            "mean_absolute": round(fit.mean_absolute, 4),
            "max_absolute": round(fit.max_absolute, 4),
        },
    }
    if args.shape == "sphere" and args.diameter is not None:
        payload["diameter_mm"] = {
            "measured": args.diameter,
            "estimated": round(fit.parameters["radius_mm"] * 2.0, 3),
        }

    output = result_dir / f"evaluation_{args.shape}.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print()
    print(f"保存先: {output}")

    if pixels is not None:
        depth_preview = result_dir / "depth.png"
        shape = cv2.imread(str(depth_preview)).shape[:2] if depth_preview.is_file() else None
        if shape is not None:
            image = evaluate.residual_map(fit, pixels, shape, limit_mm=args.threshold)
            residual_path = result_dir / f"residual_{args.shape}.png"
            cv2.imwrite(str(residual_path), image)
            print(f"        {residual_path}")
            print()
            print("残差の画像が一様なノイズに見えれば正常です。"
                  "縞や勾配が見える場合は系統誤差です。")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
