"""カメラとプロジェクタのキャリブレーション。

プロジェクタは「光を投げるカメラ」として扱えます。平面のチェッカーボードに
グレイコードを投影して撮影すると、ボード上の各交点がプロジェクタのどの画素
から照らされていたかが分かります。これを「プロジェクタが撮影した交点の座標」
とみなせば、カメラと同じ手順で内部パラメータを推定でき、さらに両者をステレオ
対として外部パラメータを求められます。

交点のプロジェクタ座標は、交点のまわりのデコード結果から局所的な射影変換を
当てはめて求めます。デコード結果は投影画素単位に量子化されていますが、ボードは
平面なのでカメラ座標とプロジェクタ座標は射影変換で結ばれます。周辺の多数の点
から変換を当てはめることで、交点のサブピクセル位置を精度よく移せます。

参考: D. Moreno and G. Taubin, "Simple, Accurate, and Robust Projector-Camera
Calibration," 3DIMPVT 2012.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .config import CalibrationConfig, Config
from .decode import DecodeResult

# 交点のサブピクセル位置を詰めるときの探索窓と終了条件。
_SUBPIX_WINDOW = (11, 11)
_SUBPIX_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# 局所的な射影変換を当てはめるのに最低限必要な対応点の数。
_MIN_LOCAL_POINTS = 32


@dataclass(frozen=True)
class CalibrationResult:
    camera_matrix: np.ndarray
    camera_distortion: np.ndarray
    projector_matrix: np.ndarray
    projector_distortion: np.ndarray
    rotation: np.ndarray
    translation: np.ndarray
    camera_error: float
    projector_error: float
    stereo_error: float
    camera_size: tuple[int, int]
    projector_size: tuple[int, int]
    pose_names: list[str]

    @property
    def baseline_mm(self) -> float:
        """カメラとプロジェクタの距離（mm）。"""
        return float(np.linalg.norm(self.translation))


def board_object_points(calibration: CalibrationConfig) -> np.ndarray:
    """ボード座標系での交点の三次元位置（Z = 0 の平面）。

    単位は mm です。ここで実寸を与えることで、復元結果が実スケールになります。
    """
    columns, rows = calibration.board_size
    points = np.zeros((rows * columns, 3), dtype=np.float32)
    grid = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2)
    points[:, :2] = grid * calibration.square_size_mm
    return points


def to_display(image: np.ndarray) -> np.ndarray:
    """RAW（Bayer 16bit）の撮影画像を、交点検出に使う 8bit グレースケールにする。

    検出はデモザイクした見た目の画像に対して行います。デコードと違い、ここでは
    隣接画素が混ざることより、模様がはっきり見えることが重要です。

    明るさの正規化には上下 1% を除いた範囲を使います。最小値と最大値で
    正規化すると、投影光の鏡面反射のような一点の極端な輝度に引きずられ、
    ボードのコントラストが狭い範囲に潰れてしまうためです。
    """
    if image.dtype != np.uint8:
        low, high = np.percentile(image, (1.0, 99.0))
        if high <= low:
            low, high = float(image.min()), float(max(image.max(), image.min() + 1))
        scaled = (image.astype(np.float32) - low) * (255.0 / (high - low))
        image = np.clip(scaled, 0, 255).astype(np.uint8)
    if image.ndim == 2:
        color = cv2.cvtColor(image, cv2.COLOR_BayerRG2BGR)
        return cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _equalized(gray: np.ndarray) -> np.ndarray:
    """照明むらを局所的に補正する。

    投影光が片側に偏っていると、盤面の端で白マスと黒マスの明るさが入れ替わる
    ことがあります。局所的に補正しておくと検出できる場合があります。
    """
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)


def _find(gray: np.ndarray, board_size: tuple[int, int]) -> np.ndarray | None:
    """1 枚のグレースケール画像から交点を探す。

    まず findChessboardCornersSB を使います。従来の findChessboardCorners より
    照明むらとぼけに強く、サブピクセル位置まで返してくれるためです。見つから
    なければ、補正した画像と従来の検出器も順に試します。
    """
    found, corners = cv2.findChessboardCornersSB(
        gray, board_size, flags=cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_ACCURACY
    )
    if found:
        return corners

    found, corners = cv2.findChessboardCornersSB(
        _equalized(gray), board_size, flags=cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_ACCURACY
    )
    if found:
        return corners

    found, corners = cv2.findChessboardCorners(
        gray,
        board_size,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not found:
        return None
    return cv2.cornerSubPix(gray, corners, _SUBPIX_WINDOW, (-1, -1), _SUBPIX_CRITERIA)


def detect_corners(
    white_image: np.ndarray, board_size: tuple[int, int]
) -> np.ndarray | None:
    """全白画像からチェッカーボードの交点を検出する。

    board_size は「内側の交点の数」です。マスが 9 x 6 のボードなら 8 x 5 です。
    見つからなければ None を返します。
    """
    return _find(to_display(white_image), board_size)


def probe_board_size(
    white_image: np.ndarray, maximum: int = 12
) -> list[tuple[int, int]]:
    """どの交点数なら検出できるかを総当たりで調べる。

    ボードの仕様が「マスの数」なのか「交点の数」なのか分からないときに使います。
    小さい組み合わせは盤面の一部にも当てはまるので、見つかったもののうち最大の
    ものが本来の交点数です。
    """
    gray = to_display(white_image)
    found_sizes = []
    for columns in range(3, maximum + 1):
        for rows in range(3, columns + 1):
            if _find(gray, (columns, rows)) is not None:
                found_sizes.append((columns, rows))
    return found_sizes


def projector_corners(
    decoded: DecodeResult, camera_corners: np.ndarray, window: int
) -> np.ndarray | None:
    """カメラ画像上の交点を、プロジェクタ画像上の座標へ移す。

    各交点のまわり ±window の範囲にあるデコード済み画素から、カメラ座標 →
    プロジェクタ座標の射影変換を RANSAC で当てはめ、交点を変換します。
    1 点でも変換を当てはめられなければ None を返します（姿勢ごと捨てます）。
    """
    height, width = decoded.mask.shape
    results = np.zeros((camera_corners.shape[0], 1, 2), dtype=np.float32)

    for index, corner in enumerate(camera_corners.reshape(-1, 2)):
        center_x, center_y = float(corner[0]), float(corner[1])
        left = max(int(center_x) - window, 0)
        right = min(int(center_x) + window + 1, width)
        top = max(int(center_y) - window, 0)
        bottom = min(int(center_y) + window + 1, height)

        local_mask = decoded.mask[top:bottom, left:right]
        if int(local_mask.sum()) < _MIN_LOCAL_POINTS:
            return None

        rows, columns = np.nonzero(local_mask)
        source = np.stack(
            [columns + left, rows + top], axis=1
        ).astype(np.float32)
        target = np.stack(
            [
                decoded.proj_x[top:bottom, left:right][local_mask],
                decoded.proj_y[top:bottom, left:right][local_mask],
            ],
            axis=1,
        ).astype(np.float32)

        homography, _ = cv2.findHomography(source, target, cv2.RANSAC, 3.0)
        if homography is None:
            return None

        moved = cv2.perspectiveTransform(
            np.array([[[center_x, center_y]]], dtype=np.float32), homography
        )
        results[index, 0] = moved[0, 0]

    return results


def calibrate(
    config: Config,
    object_points: list[np.ndarray],
    camera_points: list[np.ndarray],
    projector_points: list[np.ndarray],
    camera_size: tuple[int, int],
    pose_names: list[str],
) -> CalibrationResult:
    """カメラ・プロジェクタそれぞれの内部パラメータと、両者の相対姿勢を求める。"""
    if len(object_points) < config.calibration.min_poses:
        raise ValueError(
            f"有効な姿勢が {len(object_points)} 件しかありません"
            f"（最低 {config.calibration.min_poses} 件必要です）"
        )

    projector_size = config.projector.size

    camera_error, camera_matrix, camera_distortion, _, _ = cv2.calibrateCamera(
        object_points, camera_points, camera_size, None, None
    )
    (
        projector_error,
        projector_matrix,
        projector_distortion,
        _,
        _,
    ) = cv2.calibrateCamera(object_points, projector_points, projector_size, None, None)

    # 内部パラメータは上で求めた値に固定し、相対姿勢だけを推定します。
    stereo_error, *_, rotation, translation, _, _ = cv2.stereoCalibrate(
        object_points,
        camera_points,
        projector_points,
        camera_matrix,
        camera_distortion,
        projector_matrix,
        projector_distortion,
        camera_size,
        flags=cv2.CALIB_FIX_INTRINSIC,
    )

    return CalibrationResult(
        camera_matrix=camera_matrix,
        camera_distortion=camera_distortion,
        projector_matrix=projector_matrix,
        projector_distortion=projector_distortion,
        rotation=rotation,
        translation=translation,
        camera_error=float(camera_error),
        projector_error=float(projector_error),
        stereo_error=float(stereo_error),
        camera_size=camera_size,
        projector_size=projector_size,
        pose_names=pose_names,
    )


def save(result: CalibrationResult, path: Path) -> None:
    """キャリブレーション結果を JSON で保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "calibrated_at": datetime.now().isoformat(timespec="seconds"),
        "camera_width": result.camera_size[0],
        "camera_height": result.camera_size[1],
        "projector_width": result.projector_size[0],
        "projector_height": result.projector_size[1],
        "camera_matrix": result.camera_matrix.tolist(),
        "camera_distortion": result.camera_distortion.ravel().tolist(),
        "projector_matrix": result.projector_matrix.tolist(),
        "projector_distortion": result.projector_distortion.ravel().tolist(),
        "rotation": result.rotation.tolist(),
        "translation": result.translation.ravel().tolist(),
        "baseline_mm": round(result.baseline_mm, 2),
        "reprojection_error": {
            "camera": round(result.camera_error, 4),
            "projector": round(result.projector_error, 4),
            "stereo": round(result.stereo_error, 4),
        },
        "poses": result.pose_names,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load(path: Path) -> CalibrationResult:
    """保存したキャリブレーション結果を読み込む。"""
    if not path.is_file():
        raise FileNotFoundError(
            f"キャリブレーション結果がありません: {path}"
            "（先に scripts/05_calibrate.py を実行してください）"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = payload["reprojection_error"]
    return CalibrationResult(
        camera_matrix=np.array(payload["camera_matrix"], dtype=np.float64),
        camera_distortion=np.array(payload["camera_distortion"], dtype=np.float64),
        projector_matrix=np.array(payload["projector_matrix"], dtype=np.float64),
        projector_distortion=np.array(
            payload["projector_distortion"], dtype=np.float64
        ),
        rotation=np.array(payload["rotation"], dtype=np.float64),
        translation=np.array(payload["translation"], dtype=np.float64).reshape(3, 1),
        camera_error=errors["camera"],
        projector_error=errors["projector"],
        stereo_error=errors["stereo"],
        camera_size=(payload["camera_width"], payload["camera_height"]),
        projector_size=(payload["projector_width"], payload["projector_height"]),
        pose_names=payload["poses"],
    )
