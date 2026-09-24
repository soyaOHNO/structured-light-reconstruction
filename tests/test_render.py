"""点群の描画のテスト。

    uv run --no-sync python tests/test_render.py

形が分かっている点群を描き、視点を変えたときに見え方が正しく変わるかを
確認します。描画は目で見て判断するものですが、「視点を変えても何も変わらない」
「点が画面外に出てしまう」といった壊れ方は機械的に検出できます。
"""

from __future__ import annotations

import sys

import numpy as np

from slr import render

BACKGROUND = 20


def make_box(seed: int = 0) -> np.ndarray:
    """奥行きのある直方体の表面上の点。"""
    generator = np.random.default_rng(seed)
    points = generator.uniform(-1.0, 1.0, (5000, 3))
    points[:, 2] *= 0.3  # 薄い板状にして、回転で見え方が変わるようにする
    return points * np.array([100.0, 60.0, 40.0]) + np.array([0.0, 0.0, 700.0])


def foreground(image: np.ndarray) -> np.ndarray:
    return (image != BACKGROUND).any(axis=2)


def extent(image: np.ndarray) -> tuple[float, float]:
    """描かれた点の広がりを、画像の幅・高さに対する割合で返す。

    点は疎なので、塗りつぶされた面積の割合では大きさを測れません。
    点が分布している範囲（外接矩形）で見ます。
    """
    mask = foreground(image)
    rows, columns = np.nonzero(mask)
    if len(rows) == 0:
        return 0.0, 0.0
    height, width = mask.shape
    return (columns.max() - columns.min() + 1) / width, (rows.max() - rows.min() + 1) / height


def points_land_inside_the_frame() -> None:
    image = render.render(make_box(), None, size=(400, 300), background=BACKGROUND)
    assert image.shape == (300, 400, 3), f"画像の形が {image.shape} です"

    mask = foreground(image)
    assert mask.any(), "何も描かれていません"

    horizontal, vertical = extent(image)
    assert horizontal > 0.4, f"横方向の広がりが {horizontal * 100:.0f}% しかありません"
    assert vertical > 0.2, f"縦方向の広がりが {vertical * 100:.0f}% しかありません"

    # 余白が確保され、点が縁に張り付いていないこと
    assert not mask[0].any() and not mask[-1].any(), "点が上下の縁に達しています"
    assert not mask[:, 0].any() and not mask[:, -1].any(), "点が左右の縁に達しています"
    print(
        f"  枠内に収まる: OK（広がり 横 {horizontal * 100:.0f}% 縦 {vertical * 100:.0f}%、余白あり）"
    )


def rotation_changes_the_image() -> None:
    points = make_box()
    front = render.render(points, None, yaw_deg=0.0, size=(400, 300))
    turned = render.render(points, None, yaw_deg=45.0, size=(400, 300))
    difference = float((front != turned).mean())
    assert difference > 0.05, f"視点を 45 度変えても {difference * 100:.1f}% しか変わりません"
    print(f"  視点で見え方が変わる: OK（45 度で {difference * 100:.0f}% の画素が変化）")


def scale_is_stable_across_viewpoints() -> None:
    """どの向きから見ても、画面に占める大きさが極端に変わらないこと。"""
    points = make_box()
    widths = [
        extent(render.render(points, None, yaw_deg=angle, size=(400, 300)))[0]
        for angle in (-60.0, -30.0, 0.0, 30.0, 60.0)
    ]
    assert min(widths) > 0.2, f"最小の広がりが {min(widths) * 100:.0f}% しかありません"
    assert max(widths) / min(widths) < 2.0, (
        f"視点によって広がりが {max(widths) / min(widths):.1f} 倍も変わります"
    )
    print(
        "  倍率が安定: OK（横の広がり "
        + " / ".join(f"{w * 100:.0f}%" for w in widths)
        + "）"
    )


def nearer_points_cover_farther_ones() -> None:
    """手前の点が奥の点を隠すこと（遮蔽が正しいこと）。"""
    far = np.zeros((2000, 3))
    far[:, :2] = np.random.default_rng(1).uniform(-50, 50, (2000, 2))
    far[:, 2] = 800.0
    near = far.copy()
    near[:, 2] = 600.0

    far_color = np.tile(np.array([[255, 0, 0]], dtype=np.uint8), (len(far), 1))
    near_color = np.tile(np.array([[0, 0, 255]], dtype=np.uint8), (len(near), 1))

    points = np.vstack([far, near])
    colors = np.vstack([far_color, near_color])
    image = render.render(points, colors, size=(300, 300), point_size=1)

    drawn = image[foreground(image)]
    blue = int((drawn[:, 2] > 128).sum())
    red = int((drawn[:, 0] > 128).sum())
    assert blue > red * 5, f"手前（青）{blue} 点に対し奥（赤）が {red} 点見えています"
    print(f"  遮蔽が正しい: OK（手前 {blue} 点 / 奥 {red} 点）")


def turntable_produces_the_requested_frames() -> None:
    frames = render.turntable(make_box(), None, frames=8, size=(200, 150))
    assert len(frames) == 8, f"コマ数が {len(frames)} です"
    assert all(frame.shape == (150, 200, 3) for frame in frames), "コマの形が揃っていません"
    unique = {frame.tobytes() for frame in frames}
    assert len(unique) > 4, f"異なるコマが {len(unique)} 種類しかありません"
    print(f"  連続画像: OK（8 コマ中 {len(unique)} 種類が異なる）")


def empty_input_is_rejected() -> None:
    try:
        render.render(np.zeros((0, 3)), None)
    except ValueError:
        print("  空の点群を拒否: OK")
        return
    raise AssertionError("点が 0 個なのに例外が出ませんでした")


def main() -> int:
    print("描画:")
    points_land_inside_the_frame()
    rotation_changes_the_image()
    scale_is_stable_across_viewpoints()
    nearer_points_cover_farther_ones()
    turntable_produces_the_requested_frames()

    print("\n異常系:")
    empty_input_is_rejected()

    print("\nすべて成功しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
