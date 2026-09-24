"""復元した点群の精度を、既知形状との比較で評価する。

復元結果は見た目がもっともらしくても、誤差の大きさは分かりません。形が
分かっているもの（平らな板、球）を計測し、その形からのずれを測ることで、
初めて数値としての精度が出ます。

平面の場合、残差の広がりがそのまま奥行き方向のノイズの大きさになります。
球の場合は、推定された半径と実際の半径の差が、系統的な誤差（スケールの
ずれ）を表します。平面ではスケールのずれが見えないので、両方を測ると
性質の違う誤差を切り分けられます。

当てはめには RANSAC を使います。指定した範囲に計測対象以外のもの（背景や
台）が混ざっていても、少数派として除外されるためです。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class FitResult:
    """当てはめの結果。

    residuals は当てはめた形状からの符号つきの距離（mm）で、inliers が
    当てはめに使われた点です。統計値は inlier についてのものです。
    """

    residuals: np.ndarray
    inliers: np.ndarray
    parameters: dict

    @property
    def rms(self) -> float:
        return float(np.sqrt(np.mean(self.residuals[self.inliers] ** 2)))

    @property
    def mean_absolute(self) -> float:
        return float(np.mean(np.abs(self.residuals[self.inliers])))

    @property
    def max_absolute(self) -> float:
        return float(np.max(np.abs(self.residuals[self.inliers])))

    @property
    def inlier_ratio(self) -> float:
        return float(self.inliers.mean())


def _plane_residuals(points: np.ndarray, plane: np.ndarray) -> np.ndarray:
    """点から平面までの符号つき距離。plane は [nx, ny, nz, d] で単位法線。"""
    return points @ plane[:3] + plane[3]


def _fit_plane_least_squares(points: np.ndarray) -> np.ndarray:
    """最小二乗で平面を当てはめる（主成分分析による直交回帰）。

    z = ax + by + c の形で解くと、平面がカメラの視線と平行に近いときに
    破綻します。重心まわりの分散が最も小さい方向を法線とすることで、
    どの向きの平面でも同じ精度で扱えます。
    """
    centroid = points.mean(axis=0)
    _, _, vectors = np.linalg.svd(points - centroid, full_matrices=False)
    normal = vectors[-1]
    normal = normal / np.linalg.norm(normal)
    return np.array([*normal, -normal @ centroid])


def fit_plane(
    points: np.ndarray,
    threshold_mm: float = 2.0,
    iterations: int = 200,
    seed: int = 0,
) -> FitResult:
    """点群に平面を当てはめる（RANSAC で外れ値を除いてから最小二乗）。"""
    if len(points) < 3:
        raise ValueError(f"平面の当てはめには 3 点以上必要です（{len(points)} 点）")

    generator = np.random.default_rng(seed)
    best_inliers = np.zeros(len(points), dtype=bool)

    for _ in range(iterations):
        sample = points[generator.choice(len(points), 3, replace=False)]
        candidate = _fit_plane_least_squares(sample)
        inliers = np.abs(_plane_residuals(points, candidate)) < threshold_mm
        if inliers.sum() > best_inliers.sum():
            best_inliers = inliers

    if best_inliers.sum() < 3:
        raise ValueError("平面に乗る点が見つかりません。範囲やしきい値を見直してください。")

    # 見つかった内点だけで当てはめ直す
    plane = _fit_plane_least_squares(points[best_inliers])
    residuals = _plane_residuals(points, plane)
    inliers = np.abs(residuals) < threshold_mm

    normal = plane[:3]
    if normal[2] > 0:  # 法線をカメラ向き（-Z 側）に揃える
        normal, plane = -normal, -plane

    # カメラ光軸（Z 軸）に対する傾き
    tilt = float(np.degrees(np.arccos(min(abs(normal[2]), 1.0))))
    distance = float(abs(plane[3]))

    return FitResult(
        residuals=residuals,
        inliers=inliers,
        parameters={
            "normal": normal.tolist(),
            "distance_mm": round(distance, 3),
            "tilt_deg": round(tilt, 3),
        },
    )


def fit_sphere(
    points: np.ndarray,
    threshold_mm: float = 2.0,
    iterations: int = 200,
    seed: int = 0,
) -> FitResult:
    """点群に球を当てはめる。

    半径と中心は線形最小二乗で解けます。球の方程式 |p - c|² = r² を展開すると
    |p|² = 2c·p + (r² - |c|²) となり、c と (r² - |c|²) について線形だからです。
    """
    if len(points) < 4:
        raise ValueError(f"球の当てはめには 4 点以上必要です（{len(points)} 点）")

    def solve(subset: np.ndarray) -> tuple[np.ndarray, float]:
        matrix = np.c_[2.0 * subset, np.ones(len(subset))]
        target = (subset**2).sum(axis=1)
        solution, *_ = np.linalg.lstsq(matrix, target, rcond=None)
        center = solution[:3]
        squared = solution[3] + center @ center
        if squared <= 0:
            raise ValueError("球として解けません")
        return center, float(np.sqrt(squared))

    generator = np.random.default_rng(seed)
    best_inliers = np.zeros(len(points), dtype=bool)

    for _ in range(iterations):
        try:
            center, radius = solve(points[generator.choice(len(points), 4, replace=False)])
        except (ValueError, np.linalg.LinAlgError):
            continue
        distances = np.linalg.norm(points - center, axis=1) - radius
        inliers = np.abs(distances) < threshold_mm
        if inliers.sum() > best_inliers.sum():
            best_inliers = inliers

    if best_inliers.sum() < 4:
        raise ValueError("球に乗る点が見つかりません。範囲やしきい値を見直してください。")

    center, radius = solve(points[best_inliers])
    residuals = np.linalg.norm(points - center, axis=1) - radius
    inliers = np.abs(residuals) < threshold_mm

    return FitResult(
        residuals=residuals,
        inliers=inliers,
        parameters={
            "center_mm": [round(float(value), 3) for value in center],
            "radius_mm": round(float(radius), 3),
            "distance_mm": round(float(np.linalg.norm(center)), 3),
        },
    )


def select_roi(
    points: np.ndarray, pixels: np.ndarray, roi: tuple[int, int, int, int]
) -> np.ndarray:
    """カメラ画像上の矩形で点を絞り込む。

    depth.png を見ながら評価したい範囲を決められるよう、三次元座標ではなく
    画面上の座標で指定します。返り値は points に対する真偽値の配列です。
    """
    x, y, width, height = roi
    return (
        (pixels[:, 0] >= x)
        & (pixels[:, 0] < x + width)
        & (pixels[:, 1] >= y)
        & (pixels[:, 1] < y + height)
    )


def _diverging_lut() -> np.ndarray:
    """0 を白、負を青、正を赤にする配色表。

    残差には符号があるので、中央を基準に両側へ色が分かれる配色でないと
    「どちら側にずれているか」が読み取れません。OpenCV の組み込み配色には
    この性質を持つものがないため、自前で作ります。
    """
    levels = np.arange(256, dtype=np.float32)
    ratio = np.abs(levels - 127.5) / 127.5
    fade = (1.0 - ratio) * 255.0

    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    negative = levels < 127.5
    # OpenCV は BGR 順
    lut[negative, 0, 0] = 255                      # 青
    lut[negative, 0, 1] = fade[negative]
    lut[negative, 0, 2] = fade[negative]
    lut[~negative, 0, 0] = fade[~negative]
    lut[~negative, 0, 1] = fade[~negative]
    lut[~negative, 0, 2] = 255                     # 赤
    return lut


def residual_map(
    result: FitResult,
    pixels: np.ndarray,
    shape: tuple[int, int],
    limit_mm: float,
) -> np.ndarray:
    """残差を色で表した画像を作る。

    誤差が一様に散らばっていればノイズですが、縞や勾配として現れる場合は
    系統的な誤差です。分布の形を見ることで原因の見当がつきます。
    """
    canvas = np.zeros(shape, dtype=np.uint8)
    valid = np.zeros(shape, dtype=bool)

    normalized = np.clip(result.residuals / limit_mm, -1.0, 1.0)
    canvas[pixels[:, 1], pixels[:, 0]] = ((normalized + 1.0) * 127.5).astype(np.uint8)
    valid[pixels[:, 1], pixels[:, 0]] = True

    colored = cv2.applyColorMap(canvas, _diverging_lut())
    colored[~valid] = 0
    return colored
