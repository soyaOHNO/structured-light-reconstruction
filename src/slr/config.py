"""設定ファイルの読み込みと、プロジェクトルート基準のパス解決。

スクリプトをどのディレクトリから実行しても同じ場所を指すように、パスはすべて
プロジェクトルート（pyproject.toml のあるディレクトリ）から解決します。
カレントディレクトリに依存する相対パスは使いません。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """pyproject.toml を持つ最も近い親ディレクトリをプロジェクトルートとして返す。"""
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError(
        f"pyproject.toml が見つかりません（探索の起点: {current}）"
    )


PROJECT_ROOT = find_project_root()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.toml"


@dataclass(frozen=True)
class ProjectorConfig:
    width: int
    height: int
    auto: bool
    x: int
    y: int

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def label(self) -> str:
        """パターンディレクトリ名などに使う解像度ラベル（例: 1920x1080）。"""
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class CameraConfig:
    pixel_format: str
    exposure_time_us: float
    gain_db: float
    gamma: float
    white_balance_red: float
    white_balance_blue: float
    frames_per_pattern: int
    buffer_handling: str


@dataclass(frozen=True)
class PatternConfig:
    include_white_black: bool


@dataclass(frozen=True)
class CaptureConfig:
    warmup_sec: float


@dataclass(frozen=True)
class DecodeConfig:
    mask_threshold: float
    bit_threshold: float
    skip_fine_bits: int


@dataclass(frozen=True)
class CalibrationConfig:
    columns: int
    rows: int
    square_size_mm: float
    ambient_exposure_us: float
    min_poses: int
    corner_window: int

    @property
    def board_size(self) -> tuple[int, int]:
        """cv2.findChessboardCorners に渡す (列, 行) の交点数。"""
        return self.columns, self.rows


@dataclass(frozen=True)
class ReconstructConfig:
    min_depth_mm: float
    max_depth_mm: float
    max_reprojection_error_px: float


@dataclass(frozen=True)
class PathConfig:
    patterns: Path
    raw: Path
    results: Path


@dataclass(frozen=True)
class Config:
    projector: ProjectorConfig
    camera: CameraConfig
    pattern: PatternConfig
    capture: CaptureConfig
    decode: DecodeConfig
    calibration: CalibrationConfig
    reconstruct: ReconstructConfig
    paths: PathConfig
    source: Path

    @classmethod
    def load(cls, path: Path | str | None = None) -> Config:
        config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        if not config_path.is_file():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

        return cls(
            projector=ProjectorConfig(**raw["projector"]),
            camera=CameraConfig(**raw["camera"]),
            pattern=PatternConfig(**raw["pattern"]),
            capture=CaptureConfig(**raw["capture"]),
            decode=DecodeConfig(**raw["decode"]),
            calibration=CalibrationConfig(**raw["calibration"]),
            reconstruct=ReconstructConfig(**raw["reconstruct"]),
            paths=PathConfig(
                **{key: PROJECT_ROOT / value for key, value in raw["paths"].items()}
            ),
            source=config_path,
        )

    @property
    def pattern_dir(self) -> Path:
        """この投影解像度に対応するパターンディレクトリ。

        解像度をディレクトリ名に含めることで、別解像度のパターンを
        取り違えて投影する事故を防ぎます。
        """
        return self.paths.patterns / self.projector.label

    def raw_dir(self, name: str) -> Path:
        """撮影データの保存先（実験ごと）。"""
        return self.paths.raw / name

    def result_dir(self, name: str) -> Path:
        """処理結果の保存先（実験ごと）。"""
        return self.paths.results / name
