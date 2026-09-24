"""グレイコードパターンの生成・保存・読み込み。

OpenCV の ``cv2.structured_light.GrayCodePattern`` を使います。生成される
パターンは水平・垂直の両方向を含み、それぞれに反転した相補パターンが
対になっています。デコード時に同じ並び順が必要なので、並び順は manifest.json
に記録して撮影・デコードの各段階で参照します。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .config import Config

MANIFEST_NAME = "manifest.json"

# 全白・全黒のファイル名。撮影側もこの名前で保存するため、定数で共有します。
WHITE_NAME = "white"
BLACK_NAME = "black"


@dataclass(frozen=True)
class PatternSet:
    """投影するパターン一式。

    ``names`` と ``images`` は同じ順序で対応します。撮影画像もこの順序・
    この名前で保存するため、デコード時にファイル名で突き合わせられます。
    """

    names: list[str]
    images: list[np.ndarray]
    projector_size: tuple[int, int]
    graycode_count: int

    def __len__(self) -> int:
        return len(self.names)

    def __iter__(self):
        return zip(self.names, self.images, strict=True)


def create_graycode(config: Config) -> cv2.structured_light.GrayCodePattern:
    """設定の投影解像度に対応する GrayCodePattern を作る。

    デコード時も必ずこの関数で作った同じ設定のオブジェクトを使ってください。
    解像度が違うとビット数が変わり、デコード結果が無意味になります。
    """
    width, height = config.projector.size
    return cv2.structured_light.GrayCodePattern.create(width, height)


def build(config: Config) -> PatternSet:
    """設定に従ってパターン画像を生成する（ファイルには書き出さない）。"""
    graycode = create_graycode(config)
    ok, images = graycode.generate()
    if not ok:
        raise RuntimeError("グレイコードパターンの生成に失敗しました")

    images = list(images)
    names = [f"pattern_{index:02d}" for index in range(len(images))]
    graycode_count = len(images)

    if config.pattern.include_white_black:
        # 有効画素マスク用の全白・全黒。OpenCV が推奨する輝度を使います。
        width, height = config.projector.size
        black = np.zeros((height, width), dtype=np.uint8)
        white = np.zeros((height, width), dtype=np.uint8)
        black, white = graycode.getImagesForShadowMasks(black, white)
        names += [WHITE_NAME, BLACK_NAME]
        images += [white, black]

    return PatternSet(
        names=names,
        images=images,
        projector_size=config.projector.size,
        graycode_count=graycode_count,
    )


def save(pattern_set: PatternSet, directory: Path) -> Path:
    """パターン画像と manifest.json を書き出す。"""
    directory.mkdir(parents=True, exist_ok=True)

    for name, image in pattern_set:
        path = directory / f"{name}.png"
        if not cv2.imwrite(str(path), image):
            raise RuntimeError(f"パターンの保存に失敗しました: {path}")

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "projector_width": pattern_set.projector_size[0],
        "projector_height": pattern_set.projector_size[1],
        "graycode_count": pattern_set.graycode_count,
        "total_count": len(pattern_set),
        "names": pattern_set.names,
    }
    manifest_path = directory / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest_path


def load_manifest(directory: Path) -> dict:
    """保存済みパターンの manifest.json を読む。"""
    path = directory / MANIFEST_NAME
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} がありません。先に scripts/01_generate_patterns.py を実行してください。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load(config: Config) -> tuple[list[str], list[Path]]:
    """生成済みパターンの名前とファイルパスを、投影順に返す。

    manifest の解像度が設定と食い違っている場合はここで止めます。解像度の
    取り違えは撮影を一巡させた後に気づくと丸ごとやり直しになるためです。
    """
    directory = config.pattern_dir
    manifest = load_manifest(directory)

    expected = config.projector.size
    actual = (manifest["projector_width"], manifest["projector_height"])
    if actual != expected:
        raise ValueError(
            f"パターンの解像度 {actual[0]}x{actual[1]} が設定 "
            f"{expected[0]}x{expected[1]} と一致しません。"
            f"（{config.source} を確認するか、パターンを生成し直してください）"
        )

    names = list(manifest["names"])
    paths = [directory / f"{name}.png" for name in names]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"パターン画像が {len(missing)} 枚不足しています: {', '.join(missing[:5])}"
        )
    return names, paths
