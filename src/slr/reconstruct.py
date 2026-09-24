"""対応マップとキャリブレーション結果から三次元点群を復元する。

デコードで「カメラのこの画素は、プロジェクタのこの画素から照らされていた」
という対応が得られています。キャリブレーションからは、その 2 つの画素が
それぞれ空間のどの向きの光線に対応するかが分かります。2 本の光線の交点が
対象物の表面です。

座標系はカメラを原点とし、単位は mm です（キャリブレーションでボードの実寸を
mm で与えているため）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .calibration import CalibrationResult
from .config import Config
from .decode import DecodeResult


@dataclass(frozen=True)
class PointCloud:
    """復元した点群。

    points は (N, 3) の mm 単位の座標、colors は (N, 3) の RGB（uint8）、
    pixels は各点がどのカメラ画素から来たかを示す (N, 2) の (x, y) です。
    """

    points: np.ndarray
    colors: np.ndarray | None
    pixels: np.ndarray
    errors: np.ndarray

    def __len__(self) -> int:
        return len(self.points)

    @property
    def depth_range(self) -> tuple[float, float]:
        z = self.points[:, 2]
        return float(z.min()), float(z.max())


def _projection_matrices(
    calibration: CalibrationResult,
) -> tuple[np.ndarray, np.ndarray]:
    """正規化座標系での投影行列。

    歪みを除いた正規化座標を使うので、内部パラメータは含めません。カメラを
    原点、プロジェクタをその相対姿勢に置きます。
    """
    camera = np.hstack([np.eye(3), np.zeros((3, 1))])
    projector = np.hstack([calibration.rotation, calibration.translation])
    return camera, projector


def _reprojection_errors(
    points: np.ndarray,
    camera_pixels: np.ndarray,
    projector_pixels: np.ndarray,
    calibration: CalibrationResult,
) -> np.ndarray:
    """各点を両方の像に投影し直して、元の画素とのずれを測る。

    2 本の光線がきれいに交わらなかった点ほど、この値が大きくなります。
    デコードを誤った画素を落とすのに使います。
    """
    zero = np.zeros((3, 1))
    camera_projected, _ = cv2.projectPoints(
        points, zero, zero, calibration.camera_matrix, calibration.camera_distortion
    )
    projector_projected, _ = cv2.projectPoints(
        points,
        cv2.Rodrigues(calibration.rotation)[0],
        calibration.translation,
        calibration.projector_matrix,
        calibration.projector_distortion,
    )
    camera_error = np.linalg.norm(
        camera_projected.reshape(-1, 2) - camera_pixels, axis=1
    )
    projector_error = np.linalg.norm(
        projector_projected.reshape(-1, 2) - projector_pixels, axis=1
    )
    return np.maximum(camera_error, projector_error)


def triangulate(
    decoded: DecodeResult,
    calibration: CalibrationResult,
    min_depth_mm: float,
    max_depth_mm: float,
    max_error_px: float,
    color_image: np.ndarray | None = None,
) -> PointCloud:
    """有効画素をすべて三角測量し、条件を満たす点だけを返す。"""
    rows, columns = np.nonzero(decoded.mask)
    if len(rows) == 0:
        raise ValueError("有効画素がありません。先にデコード結果を確認してください。")

    camera_pixels = np.stack([columns, rows], axis=1).astype(np.float64)
    projector_pixels = np.stack(
        [decoded.proj_x[decoded.mask], decoded.proj_y[decoded.mask]], axis=1
    ).astype(np.float64)

    # レンズ歪みを除き、焦点距離で割った正規化座標にする。
    camera_normalized = cv2.undistortPoints(
        camera_pixels.reshape(-1, 1, 2),
        calibration.camera_matrix,
        calibration.camera_distortion,
    ).reshape(-1, 2)
    projector_normalized = cv2.undistortPoints(
        projector_pixels.reshape(-1, 1, 2),
        calibration.projector_matrix,
        calibration.projector_distortion,
    ).reshape(-1, 2)

    camera_matrix, projector_matrix = _projection_matrices(calibration)
    homogeneous = cv2.triangulatePoints(
        camera_matrix,
        projector_matrix,
        camera_normalized.T,
        projector_normalized.T,
    )
    # 同次座標を通常の座標に戻す。w が 0 に近い点は無限遠なので捨てる。
    w = homogeneous[3]
    finite = np.abs(w) > 1e-9
    points = np.zeros((len(w), 3), dtype=np.float64)
    points[finite] = (homogeneous[:3, finite] / w[finite]).T

    depth = points[:, 2]
    keep = finite & (depth > min_depth_mm) & (depth < max_depth_mm)

    errors = np.full(len(points), np.inf)
    if keep.any():
        errors[keep] = _reprojection_errors(
            points[keep].astype(np.float32),
            camera_pixels[keep],
            projector_pixels[keep],
            calibration,
        )
        keep &= errors <= max_error_px

    colors = None
    if color_image is not None:
        rgb = _to_color(color_image)
        colors = rgb[rows[keep], columns[keep]]

    return PointCloud(
        points=points[keep].astype(np.float32),
        colors=colors,
        pixels=camera_pixels[keep].astype(np.int32),
        errors=errors[keep].astype(np.float32),
    )


def _to_color(image: np.ndarray) -> np.ndarray:
    """RAW（Bayer）の撮影画像を 8bit RGB に変換する。

    点群の色付けに使うだけなので、ここではデモザイクして構いません。
    """
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if image.dtype != np.uint8:
        low, high = np.percentile(image, (1.0, 99.0))
        if high <= low:
            low, high = float(image.min()), float(max(image.max(), image.min() + 1))
        scaled = (image.astype(np.float32) - low) * (255.0 / (high - low))
        image = np.clip(scaled, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BayerRG2BGR), cv2.COLOR_BGR2RGB)


def write_ply(cloud: PointCloud, path: Path) -> None:
    """点群を PLY（バイナリ）で書き出す。

    CloudCompare や MeshLab で開けます。点数が多いのでテキストではなく
    バイナリ形式を使います。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    count = len(cloud)
    has_color = cloud.colors is not None

    header = [
        "ply",
        "format binary_little_endian 1.0",
        f"comment created by slr on {datetime.now().isoformat(timespec='seconds')}",
        f"element vertex {count}",
        "property float x",
        "property float y",
        "property float z",
    ]
    if has_color:
        header += [
            "property uchar red",
            "property uchar green",
            "property uchar blue",
        ]
    header += ["end_header", ""]

    if has_color:
        dtype = np.dtype(
            [("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
             ("red", "u1"), ("green", "u1"), ("blue", "u1")]
        )
        records = np.empty(count, dtype=dtype)
        records["red"], records["green"], records["blue"] = cloud.colors.T
    else:
        dtype = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4")])
        records = np.empty(count, dtype=dtype)

    records["x"], records["y"], records["z"] = cloud.points.T.astype(np.float32)

    with path.open("wb") as stream:
        stream.write("\n".join(header).encode("ascii"))
        stream.write(records.tobytes())


def save(cloud: PointCloud, directory: Path, source: str) -> Path:
    """点群と統計情報を保存する。"""
    directory.mkdir(parents=True, exist_ok=True)
    ply_path = directory / "points.ply"
    write_ply(cloud, ply_path)
    np.save(directory / "points.npy", cloud.points)
    # 各点がどのカメラ画素から来たかも残す。後から画面上の範囲を指定して
    # 一部だけを評価するのに必要になる。
    np.save(directory / "pixels.npy", cloud.pixels)
    np.save(directory / "errors.npy", cloud.errors)
    if cloud.colors is not None:
        np.save(directory / "colors.npy", cloud.colors)

    near, far = cloud.depth_range
    metadata = {
        "reconstructed_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "point_count": len(cloud),
        "depth_mm": {"min": round(near, 1), "max": round(far, 1)},
        "reprojection_error_px": {
            "mean": round(float(cloud.errors.mean()), 4),
            "median": round(float(np.median(cloud.errors)), 4),
            "max": round(float(cloud.errors.max()), 4),
        },
    }
    (directory / "reconstruct.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ply_path


def depth_preview(
    cloud: PointCloud, shape: tuple[int, int]
) -> np.ndarray:
    """奥行きを色で表した確認用の画像を作る。"""
    depth = np.zeros(shape, dtype=np.float32)
    valid = np.zeros(shape, dtype=bool)
    depth[cloud.pixels[:, 1], cloud.pixels[:, 0]] = cloud.points[:, 2]
    valid[cloud.pixels[:, 1], cloud.pixels[:, 0]] = True

    near, far = cloud.depth_range
    normalized = np.zeros(shape, dtype=np.uint8)
    if far > near:
        scaled = (depth[valid] - near) / (far - near)
        normalized[valid] = np.clip(scaled * 255.0, 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)
    colored[~valid] = 0
    return colored
