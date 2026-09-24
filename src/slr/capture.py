"""パターンを投影しながら撮影する共通処理。

計測用の撮影（scripts/02_capture.py）とキャリブレーション用の撮影
（scripts/04_capture_calibration.py）の両方から使います。撮影の手順は
まったく同じで、保存先と繰り返し方だけが違うためです。
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .camera import Camera
from .config import Config
from .projector import Projector

# 進捗通知。(何枚目, 全体の枚数, パターン名, 撮影した画像) を受け取ります。
ProgressCallback = Callable[[int, int, str, np.ndarray], None]


class CaptureAborted(RuntimeError):
    """撮影中に Esc が押された。"""


def capture_sequence(
    config: Config,
    camera: Camera,
    projector: Projector,
    names: list[str],
    pattern_paths: list[Path],
    output_dir: Path,
    on_saved: ProgressCallback | None = None,
) -> float:
    """パターンを 1 枚ずつ投影して撮影し、output_dir に保存する。

    撮影画像はパターンと同じ名前で保存するので、デコード時に名前で対応
    づけられます。返り値は所要時間（秒）です。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    for index, (name, pattern_path) in enumerate(
        zip(names, pattern_paths, strict=True), start=1
    ):
        projector.show(pattern_path)

        # プロジェクタが切り替わり、その明るさで露光が一巡するのを待ちます。
        # 短すぎると前のパターンが写り込みます。
        time.sleep(config.capture.warmup_sec)

        if projector.aborted:
            raise CaptureAborted("Esc が押されたため撮影を中断しました")

        frame = camera.grab()
        destination = output_dir / f"{name}.png"
        if not cv2.imwrite(str(destination), frame):
            raise RuntimeError(f"保存に失敗しました: {destination}")

        if on_saved is not None:
            on_saved(index, len(names), name, frame)

    return time.monotonic() - started


def save_metadata(
    directory: Path,
    config: Config,
    camera: Camera,
    names: list[str],
    elapsed: float,
    extra: dict | None = None,
) -> None:
    """撮影条件を JSON で残す。

    後から「どの露光・どの解像度で撮ったか」を画像だけから復元するのは
    困難なので、必ず一緒に保存します。
    """
    metadata = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_sec": round(elapsed, 1),
        "config_source": str(config.source),
        "projector": {
            "width": config.projector.width,
            "height": config.projector.height,
        },
        "camera": {
            "model": camera.info.model if camera.info else None,
            "serial": camera.info.serial if camera.info else None,
            "pixel_format": config.camera.pixel_format,
            "exposure_time_us": config.camera.exposure_time_us,
            "gain_db": config.camera.gain_db,
            "gamma": config.camera.gamma,
            "white_balance_red": config.camera.white_balance_red,
            "white_balance_blue": config.camera.white_balance_blue,
            "frames_per_pattern": config.camera.frames_per_pattern,
        },
        "capture": {"warmup_sec": config.capture.warmup_sec},
        "pattern_names": names,
    }
    if extra:
        metadata.update(extra)

    path = directory / "metadata.json"
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def print_progress(
    index: int, total: int, name: str, frame: np.ndarray
) -> None:
    """標準的な進捗表示。"""
    print(f"  [{index:2d}/{total}] {name}  {frame.shape[1]}x{frame.shape[0]} {frame.dtype}")
