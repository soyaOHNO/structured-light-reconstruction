"""三角測量の往復テスト。

    uv run --no-sync python tests/test_reconstruct.py

既知の三次元形状を、既知のカメラ・プロジェクタに投影して対応マップを作り、
そこから三角測量で元の形状を復元できるかを確認します。三角測量は結果を
目で見ても正しさが分からない（もっともらしい形の点群が出てしまう）ので、
数値で確かめます。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

from slr import reconstruct
from slr.calibration import CalibrationResult
from slr.decode import DecodeResult

CAMERA_SIZE = (1920, 1200)
PROJECTOR_SIZE = (1920, 1080)


def rotation_about_y(degrees: float) -> np.ndarray:
    angle = np.radians(degrees)
    cos, sin = np.cos(angle), np.sin(angle)
    return np.array([[cos, 0.0, sin], [0.0, 1.0, 0.0], [-sin, 0.0, cos]])


def make_calibration(distortion: bool = False) -> CalibrationResult:
    """カメラの右 600 mm・下 300 mm にプロジェクタを置き、内側へ 25 度振った配置。

    プロジェクタの主点 cy=1200 は画像の高さ 1080 より大きく、光軸より上だけを
    投影します（レンズシフトを持つ実機と同じ）。そのため、シーンがプロジェクタの
    光軸より上に来るように、プロジェクタをカメラより下に置きます。
    """
    camera_matrix = np.array(
        [[4000.0, 0.0, 960.0], [0.0, 4000.0, 600.0], [0.0, 0.0, 1.0]]
    )
    projector_matrix = np.array(
        [[2400.0, 0.0, 960.0], [0.0, 2400.0, 1200.0], [0.0, 0.0, 1.0]]
    )
    rotation = rotation_about_y(25.0)
    center = np.array([[600.0], [300.0], [0.0]])
    translation = -rotation @ center

    zeros = np.zeros(5)
    lens = np.array([-0.15, 0.10, 0.001, -0.002, 0.0]) if distortion else zeros
    return CalibrationResult(
        camera_matrix=camera_matrix,
        camera_distortion=lens,
        projector_matrix=projector_matrix,
        projector_distortion=zeros,
        rotation=rotation,
        translation=translation,
        camera_error=0.0,
        projector_error=0.0,
        stereo_error=0.0,
        camera_size=CAMERA_SIZE,
        projector_size=PROJECTOR_SIZE,
        pose_names=[],
    )


def make_scene(
    calibration: CalibrationResult, depth_at_center: float, tilt: float
) -> tuple[DecodeResult, np.ndarray, np.ndarray]:
    """傾いた平面を撮ったときの対応マップを作る。

    カメラ画素から光線を飛ばして平面と交わらせ、その点をプロジェクタへ投影
    します。プロジェクタ座標は整数に丸めます（実際のデコード結果も投影画素
    単位に量子化されているため）。

    返り値は (対応マップ, 真の三次元点, その画素位置)。
    """
    width, height = CAMERA_SIZE
    step = 20
    columns = np.arange(200, width - 200, step)
    rows = np.arange(150, height - 150, step)
    grid_x, grid_y = np.meshgrid(columns, rows)
    pixels = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1).astype(np.float64)

    # 画素を正規化座標に直し、平面 z = depth + tilt * x と交わらせる。
    normalized = cv2.undistortPoints(
        pixels.reshape(-1, 1, 2),
        calibration.camera_matrix,
        calibration.camera_distortion,
    ).reshape(-1, 2)
    direction = np.hstack([normalized, np.ones((len(normalized), 1))])
    scale = depth_at_center / (1.0 - tilt * direction[:, 0])
    points = direction * scale[:, None]

    projected, _ = cv2.projectPoints(
        points,
        cv2.Rodrigues(calibration.rotation)[0],
        calibration.translation,
        calibration.projector_matrix,
        calibration.projector_distortion,
    )
    projected = projected.reshape(-1, 2)

    inside = (
        (projected[:, 0] >= 0)
        & (projected[:, 0] < PROJECTOR_SIZE[0])
        & (projected[:, 1] >= 0)
        & (projected[:, 1] < PROJECTOR_SIZE[1])
    )
    assert inside.mean() > 0.5, (
        f"プロジェクタの画角に入る点が {inside.mean() * 100:.0f}% しかありません。"
        "テストの配置を見直してください。"
    )

    proj_x = np.full((height, width), -1, dtype=np.int32)
    proj_y = np.full((height, width), -1, dtype=np.int32)
    mask = np.zeros((height, width), dtype=bool)

    keep = np.nonzero(inside)[0]
    ys = pixels[keep, 1].astype(int)
    xs = pixels[keep, 0].astype(int)
    proj_x[ys, xs] = np.round(projected[keep, 0]).astype(np.int32)
    proj_y[ys, xs] = np.round(projected[keep, 1]).astype(np.int32)
    mask[ys, xs] = True

    decoded = DecodeResult(
        proj_x=proj_x,
        proj_y=proj_y,
        mask=mask,
        shadow_mask=mask,
        projector_size=PROJECTOR_SIZE,
    )
    return decoded, points[keep], pixels[keep]


def recovers_a_known_plane(distortion: bool, depth: float, tilt: float) -> None:
    calibration = make_calibration(distortion)
    decoded, truth, pixels = make_scene(calibration, depth, tilt)

    cloud = reconstruct.triangulate(
        decoded,
        calibration,
        min_depth_mm=100.0,
        max_depth_mm=3000.0,
        max_error_px=1.0,
    )

    assert len(cloud) > 0, "点が 1 つも復元できませんでした"
    kept = len(cloud) / len(truth)
    assert kept > 0.95, f"復元できた点が {kept * 100:.0f}% しかありません"

    # 画素位置で真値と対応づける
    order = {(int(x), int(y)): i for i, (x, y) in enumerate(pixels)}
    indices = np.array([order[(int(x), int(y))] for x, y in cloud.pixels])
    error = np.linalg.norm(cloud.points - truth[indices], axis=1)

    label = "歪みあり" if distortion else "歪みなし"
    assert error.max() < 2.0, (
        f"{label} 深さ{depth:.0f}mm: 誤差が最大 {error.max():.2f} mm あります"
    )
    print(
        f"  {label} 深さ {depth:.0f} mm 傾き {tilt:+.2f}: OK"
        f"（{len(cloud):,} 点、誤差 中央値 {np.median(error):.3f} mm"
        f" / 最大 {error.max():.3f} mm）"
    )


def rejects_points_behind_the_camera() -> None:
    """奥行きの範囲外の点が捨てられること。"""
    calibration = make_calibration()
    decoded, _, _ = make_scene(calibration, 1000.0, 0.0)
    cloud = reconstruct.triangulate(
        decoded, calibration, min_depth_mm=1500.0, max_depth_mm=3000.0, max_error_px=1.0
    )
    assert len(cloud) == 0, f"範囲外なのに {len(cloud)} 点残りました"
    print("  奥行き範囲外を除外: OK")


def rejects_wrong_correspondences() -> None:
    """対応を壊した画素が、再投影誤差で落とされること。"""
    calibration = make_calibration()
    decoded, truth, _ = make_scene(calibration, 1000.0, 0.1)

    broken = decoded.proj_x.copy()
    rows, columns = np.nonzero(decoded.mask)
    half = len(rows) // 2
    broken[rows[:half], columns[:half]] += 60  # 大きくずらす

    damaged = DecodeResult(
        proj_x=broken,
        proj_y=decoded.proj_y,
        mask=decoded.mask,
        shadow_mask=decoded.shadow_mask,
        projector_size=PROJECTOR_SIZE,
    )
    cloud = reconstruct.triangulate(
        damaged, calibration, min_depth_mm=100.0, max_depth_mm=3000.0, max_error_px=1.0
    )
    survived = len(cloud) / len(truth)
    assert survived < 0.6, f"壊した対応が {survived * 100:.0f}% も残っています"
    print(f"  誤った対応を除外: OK（残ったのは {survived * 100:.0f}%）")


def ply_is_written_correctly() -> None:
    calibration = make_calibration()
    decoded, _, _ = make_scene(calibration, 1000.0, 0.0)
    cloud = reconstruct.triangulate(
        decoded, calibration, min_depth_mm=100.0, max_depth_mm=3000.0, max_error_px=1.0
    )

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "points.ply"
        reconstruct.write_ply(cloud, path)
        data = path.read_bytes()
        header, _, body = data.partition(b"end_header\n")
        text = header.decode("ascii")
        assert f"element vertex {len(cloud)}" in text, "点数がヘッダと合いません"
        assert len(body) == len(cloud) * 12, (
            f"本体の長さが {len(body)} バイトです"
            f"（{len(cloud)} 点 x 12 バイト = {len(cloud) * 12} のはず）"
        )
        restored = np.frombuffer(body, dtype="<f4").reshape(-1, 3)
        assert np.allclose(restored, cloud.points), "書き出した座標が一致しません"
    print(f"  PLY の書き出し: OK（{len(cloud):,} 点）")


def main() -> int:
    print("平面の復元:")
    recovers_a_known_plane(distortion=False, depth=1000.0, tilt=0.0)
    recovers_a_known_plane(distortion=False, depth=1000.0, tilt=0.15)
    recovers_a_known_plane(distortion=False, depth=600.0, tilt=0.0)
    recovers_a_known_plane(distortion=True, depth=1000.0, tilt=0.10)

    print("\n異常値の除外:")
    rejects_points_behind_the_camera()
    rejects_wrong_correspondences()

    print("\n書き出し:")
    ply_is_written_correctly()

    print("\nすべて成功しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
