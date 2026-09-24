"""点群を画像として描き出す。

点群ビューアを入れなくても形状を確認できるようにするためのものです。
視点を回した連続画像を作れば、静止画では分かりにくい奥行きが一目で
分かります。発表資料に貼る図としてもそのまま使えます。

外部のライブラリは使わず、numpy で座標を変換して奥行き順に描いています。
点群ビューアのような対話的な操作はできませんが、依存を増やさずに済みます。
"""

from __future__ import annotations

import numpy as np


def _rotation(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    """縦軸まわり（yaw）と横軸まわり（pitch）の回転。"""
    yaw, pitch = np.radians(yaw_deg), np.radians(pitch_deg)
    around_y = np.array(
        [
            [np.cos(yaw), 0.0, np.sin(yaw)],
            [0.0, 1.0, 0.0],
            [-np.sin(yaw), 0.0, np.cos(yaw)],
        ]
    )
    around_x = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(pitch), -np.sin(pitch)],
            [0.0, np.sin(pitch), np.cos(pitch)],
        ]
    )
    return around_x @ around_y


def _depth_colors(depth: np.ndarray) -> np.ndarray:
    """奥行きを青（手前）から赤（奥）へ着色する。"""
    span = depth.max() - depth.min()
    normalized = (depth - depth.min()) / span if span > 0 else np.zeros_like(depth)
    colors = np.zeros((len(depth), 3), dtype=np.uint8)
    colors[:, 0] = (normalized * 255).astype(np.uint8)          # 赤 = 奥
    colors[:, 1] = ((1.0 - np.abs(normalized * 2 - 1)) * 255).astype(np.uint8)
    colors[:, 2] = ((1.0 - normalized) * 255).astype(np.uint8)  # 青 = 手前
    return colors


def render(
    points: np.ndarray,
    colors: np.ndarray | None,
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    size: tuple[int, int] = (900, 700),
    margin: float = 0.12,
    point_size: int = 1,
    background: int = 20,
) -> np.ndarray:
    """指定した視点から点群を描画して RGB 画像を返す。

    点群の重心を中心に回転させ、画面いっぱいに収まる倍率で投影します。
    視点を変えても大きさが変わらないよう、倍率は点群の広がりから決めます。

    手前の点が奥の点を隠すよう、奥から順に描きます（画家のアルゴリズム）。
    """
    if len(points) == 0:
        raise ValueError("点がありません")

    width, height = size
    centered = points - points.mean(axis=0)
    rotated = centered @ _rotation(yaw_deg, pitch_deg).T

    # どの向きから見ても収まるよう、重心からの最大距離を基準に倍率を決める
    radius = float(np.linalg.norm(centered, axis=1).max())
    if radius <= 0:
        radius = 1.0
    scale = (min(width, height) * (1.0 - margin * 2)) / (radius * 2.0)

    x = (rotated[:, 0] * scale + width / 2.0).astype(np.int32)
    y = (rotated[:, 1] * scale + height / 2.0).astype(np.int32)
    depth = rotated[:, 2]

    inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
    x, y, depth = x[inside], y[inside], depth[inside]
    if colors is None:
        shades = _depth_colors(depth)
    else:
        shades = colors[inside]

    # 奥から手前の順に描くと、手前の点が上書きして正しい遮蔽になる
    order = np.argsort(-depth)
    x, y, shades = x[order], y[order], shades[order]

    canvas = np.full((height, width, 3), background, dtype=np.uint8)
    for offset_y in range(point_size):
        for offset_x in range(point_size):
            canvas[
                np.clip(y + offset_y, 0, height - 1),
                np.clip(x + offset_x, 0, width - 1),
            ] = shades
    return canvas


def turntable(
    points: np.ndarray,
    colors: np.ndarray | None,
    frames: int = 36,
    sweep_deg: float = 60.0,
    pitch_deg: float = -15.0,
    **kwargs,
) -> list[np.ndarray]:
    """視点を左右に振った連続画像を作る。

    一周させず往復させるのは、構造化光で得られるのが片側から見た表面だけで、
    裏側には点がないためです。真横を越えると形が分からなくなります。
    """
    angles = sweep_deg * np.sin(np.linspace(0.0, 2.0 * np.pi, frames, endpoint=False))
    return [
        render(points, colors, yaw_deg=float(angle), pitch_deg=pitch_deg, **kwargs)
        for angle in angles
    ]
