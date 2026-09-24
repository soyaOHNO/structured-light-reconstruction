"""復元した点群を画像として描き出し、形状を目で確認する。

    uv run --no-sync python scripts/08_render.py <実験名>

点群ビューアを入れなくても形が確認できるよう、視点を変えた静止画と、
視点を左右に振ったアニメーション GIF を作ります。**静止画では奥行きが
分かりにくいので、まず GIF を見てください。**

    views/view_00.png ...   視点を変えた静止画（発表資料用）
    turntable.gif           視点を振ったアニメーション

色は撮影画像から取った実際の色を使います。--color depth を付けると、
奥行きに応じた着色（手前が青、奥が赤）になり、形の起伏が分かりやすく
なります。
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
from PIL import Image

from slr import cli, render
from slr.config import Config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="実験名（data/results/ 以下のディレクトリ名）")
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument(
        "--color",
        choices=["rgb", "depth"],
        default="rgb",
        help="点の着色。rgb は撮影画像の色、depth は奥行きによる着色",
    )
    parser.add_argument("--frames", type=int, default=36, help="GIF のコマ数")
    parser.add_argument(
        "--sweep", type=float, default=60.0, help="視点を振る角度の片側の大きさ（度）"
    )
    parser.add_argument("--pitch", type=float, default=-15.0, help="見下ろす角度（度）")
    parser.add_argument("--width", type=int, default=900, help="画像の幅")
    parser.add_argument("--height", type=int, default=700, help="画像の高さ")
    parser.add_argument(
        "--point-size", type=int, default=2, help="1 点を描く大きさ（画素）"
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    result_dir = config.result_dir(args.name)
    points_path = result_dir / "points.npy"
    if not points_path.is_file():
        raise FileNotFoundError(
            f"点群がありません: {points_path}"
            "（先に scripts/06_reconstruct.py を実行してください）"
        )

    points = np.load(points_path).astype(np.float64)
    colors = None
    if args.color == "rgb":
        colors_path = result_dir / "colors.npy"
        if colors_path.is_file():
            colors = np.load(colors_path)
        else:
            print("  [注意] colors.npy がないため、奥行きによる着色にします。")
            print("         色を使うには 06_reconstruct.py を実行し直してください。")

    print(f"入力   : {points_path}")
    print(f"点数   : {len(points):,}")
    print(f"着色   : {'撮影画像の色' if colors is not None else '奥行き'}")

    options = {
        "size": (args.width, args.height),
        "point_size": args.point_size,
    }

    # 視点を変えた静止画
    views_dir = result_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    angles = [(-40.0, args.pitch), (-20.0, args.pitch), (0.0, args.pitch),
              (20.0, args.pitch), (40.0, args.pitch), (0.0, -45.0)]
    for index, (yaw, pitch) in enumerate(angles):
        image = render.render(points, colors, yaw_deg=yaw, pitch_deg=pitch, **options)
        path = views_dir / f"view_{index:02d}.png"
        Image.fromarray(image).save(path)
    print(f"静止画 : {views_dir}（{len(angles)} 枚）")

    # アニメーション
    frames = render.turntable(
        points,
        colors,
        frames=args.frames,
        sweep_deg=args.sweep,
        pitch_deg=args.pitch,
        **options,
    )
    gif_path = result_dir / "turntable.gif"
    images = [Image.fromarray(frame) for frame in frames]
    images[0].save(
        gif_path,
        save_all=True,
        append_images=images[1:],
        duration=80,
        loop=0,
        optimize=True,
    )
    size_mb = gif_path.stat().st_size / 1024 / 1024
    print(f"GIF    : {gif_path}（{len(frames)} コマ、{size_mb:.1f} MB）")

    print()
    print("確認のしかた:")
    print(f"  start {gif_path}")
    print("  視点が動いたときに、手前のものが大きく動いて見えれば立体になっています。")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
