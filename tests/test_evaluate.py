"""精度評価の当てはめのテスト。

    uv run --no-sync python tests/test_evaluate.py

既知のノイズを与えた平面・球を作り、当てはめが元のパラメータと、与えた
ノイズの大きさを取り戻せるかを確認します。精度評価そのものが間違っていると、
計測結果の良し悪しを誤って判断してしまうためです。
"""

from __future__ import annotations

import sys

import numpy as np

from slr import evaluate


def make_plane(
    normal: np.ndarray, distance: float, noise_mm: float, count: int = 4000, seed: int = 1
) -> np.ndarray:
    """指定した平面上に、法線方向へガウスノイズを載せた点を作る。"""
    generator = np.random.default_rng(seed)
    normal = normal / np.linalg.norm(normal)

    # 平面内の直交する 2 方向を作る
    helper = np.array([1.0, 0.0, 0.0])
    if abs(normal @ helper) > 0.9:
        helper = np.array([0.0, 1.0, 0.0])
    axis_u = np.cross(normal, helper)
    axis_u /= np.linalg.norm(axis_u)
    axis_v = np.cross(normal, axis_u)

    u = generator.uniform(-100.0, 100.0, count)
    v = generator.uniform(-100.0, 100.0, count)
    base = normal * distance + u[:, None] * axis_u + v[:, None] * axis_v
    return base + normal * generator.normal(0.0, noise_mm, count)[:, None]


def make_sphere(
    center: np.ndarray, radius: float, noise_mm: float, count: int = 4000, seed: int = 2
) -> np.ndarray:
    """球面の手前半分に、半径方向のノイズを載せた点を作る。"""
    generator = np.random.default_rng(seed)
    directions = generator.normal(size=(count, 3))
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    directions[:, 2] = -np.abs(directions[:, 2])  # カメラ側の半球だけ
    radii = radius + generator.normal(0.0, noise_mm, count)
    return center + directions * radii[:, None]


def plane_recovers_noise_level(noise: float) -> None:
    normal = np.array([0.3, -0.2, -1.0])
    points = make_plane(normal, 700.0, noise)
    fit = evaluate.fit_plane(points, threshold_mm=max(4.0 * noise, 0.5))

    assert abs(fit.rms - noise) < noise * 0.15 + 0.02, (
        f"ノイズ {noise} mm に対し RMS が {fit.rms:.4f} mm と出ました"
    )
    assert fit.inlier_ratio > 0.98, f"内点が {fit.inlier_ratio * 100:.0f}% しかありません"
    print(
        f"  ノイズ {noise:5.2f} mm -> RMS {fit.rms:.4f} mm"
        f"（傾き {fit.parameters['tilt_deg']:.1f}°, 距離 {fit.parameters['distance_mm']:.1f} mm）"
    )


def plane_ignores_an_intruding_object() -> None:
    """範囲に別の物体が混ざっても、多数派の平面が選ばれること。"""
    points = make_plane(np.array([0.0, 0.0, -1.0]), 700.0, 0.3, count=4000)
    intruder = make_plane(np.array([0.0, 0.0, -1.0]), 640.0, 0.3, count=900, seed=7)
    mixed = np.vstack([points, intruder])

    fit = evaluate.fit_plane(mixed, threshold_mm=2.0)
    assert abs(fit.parameters["distance_mm"] - 700.0) < 1.0, (
        f"手前の物体に引きずられました（距離 {fit.parameters['distance_mm']:.1f} mm）"
    )
    assert fit.rms < 0.5, f"RMS が {fit.rms:.3f} mm と大きすぎます"
    ratio = fit.inlier_ratio
    assert 0.75 < ratio < 0.9, f"内点の割合が {ratio * 100:.0f}% です（約 82% のはず）"
    print(f"  別物体 900 点を混入 -> 距離 {fit.parameters['distance_mm']:.2f} mm、"
          f"内点 {ratio * 100:.0f}%、RMS {fit.rms:.3f} mm")


def sphere_recovers_radius(radius: float, noise: float) -> None:
    center = np.array([10.0, -5.0, 700.0])
    points = make_sphere(center, radius, noise)
    fit = evaluate.fit_sphere(points, threshold_mm=max(4.0 * noise, 0.5))

    estimated = fit.parameters["radius_mm"]
    assert abs(estimated - radius) < 0.2, (
        f"半径 {radius} mm に対し {estimated:.3f} mm と推定されました"
    )
    center_error = np.linalg.norm(np.array(fit.parameters["center_mm"]) - center)
    assert center_error < 0.5, f"中心が {center_error:.3f} mm ずれています"
    print(
        f"  半径 {radius:5.1f} mm / ノイズ {noise:.2f} mm"
        f" -> 推定半径 {estimated:.3f} mm（誤差 {estimated - radius:+.3f} mm）、"
        f"中心のずれ {center_error:.3f} mm"
    )


def roi_selects_the_expected_points() -> None:
    points = np.zeros((100, 3))
    pixels = np.stack([np.arange(100), np.arange(100)], axis=1)
    selected = evaluate.select_roi(points, pixels, (20, 20, 30, 30))
    assert selected.sum() == 30, f"選ばれたのが {int(selected.sum())} 点です（30 点のはず）"
    assert pixels[selected][:, 0].min() == 20
    assert pixels[selected][:, 0].max() == 49
    print("  画面上の範囲指定: OK（境界は左上を含み右下を含まない）")


def too_few_points_are_rejected() -> None:
    for name, function, count in (("平面", evaluate.fit_plane, 2), ("球", evaluate.fit_sphere, 3)):
        try:
            function(np.zeros((count, 3)))
        except ValueError:
            continue
        raise AssertionError(f"{name}: 点が {count} 個なのに例外が出ませんでした")
    print("  点数不足を検出: OK")


def main() -> int:
    print("平面の当てはめ:")
    for noise in (0.1, 0.4, 1.0):
        plane_recovers_noise_level(noise)
    plane_ignores_an_intruding_object()

    print("\n球の当てはめ:")
    sphere_recovers_radius(25.0, 0.2)
    sphere_recovers_radius(50.0, 0.5)

    print("\nその他:")
    roi_selects_the_expected_points()
    too_few_points_are_rejected()

    print("\nすべて成功しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
