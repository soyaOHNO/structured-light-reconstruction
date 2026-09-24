"""撮影したグレイコード画像列から、プロジェクタ座標を復元する。

各カメラ画素について「その画素にはプロジェクタのどの画素の光が当たっていたか」
を求めます。結果は proj_x / proj_y の 2 枚のマップになり、これが三角測量の
入力になります。

OpenCV の ``GrayCodePattern`` は画素ごとの ``getProjPixel()`` しか提供して
おらず、200 万画素を Python のループで回すと現実的な時間で終わりません。
そのため復号処理は numpy で書いています。パターンの並び順は
``slr.patterns`` の生成側と対になっているため、``tests/test_decode_roundtrip.py``
で往復させて検証しています。

撮影画像は Bayer 配列の RAW のまま扱います。各ビットの判定は「同じ画素の
パターンと反転パターンの比較」なので、画素ごとの色フィルタの感度差は打ち消し
合います。デモザイクすると隣接画素が混ざって境界がなまるため、あえて
行いません。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .config import Config
from .patterns import BLACK_NAME, WHITE_NAME

# 無効画素を表す値。座標として存在しえない負の値を使います。
INVALID = -1


@dataclass(frozen=True)
class DecodeResult:
    """デコード結果。

    proj_x / proj_y は int32 で、無効画素は INVALID (-1) です。
    mask は有効画素が True の bool 配列です。
    """

    proj_x: np.ndarray
    proj_y: np.ndarray
    mask: np.ndarray
    shadow_mask: np.ndarray
    projector_size: tuple[int, int]

    @property
    def valid_ratio(self) -> float:
        return float(self.mask.mean())

    @property
    def shape(self) -> tuple[int, int]:
        return self.mask.shape


def bit_counts(width: int, height: int) -> tuple[int, int]:
    """投影解像度に対応する、横方向・縦方向のグレイコードのビット数。"""
    return math.ceil(math.log2(width)), math.ceil(math.log2(height))


def _gray_to_binary(bits: np.ndarray) -> np.ndarray:
    """グレイコードを通常の 2 進数に変換する。

    bits は (ビット数, 高さ, 幅) の bool 配列で、bits[0] が最上位ビットです。
    最上位ビットはそのまま、以降は「一つ上の桁の復号結果との排他的論理和」です。
    """
    value = np.zeros(bits.shape[1:], dtype=np.int32)
    previous = np.zeros(bits.shape[1:], dtype=bool)
    for index in range(bits.shape[0]):
        current = np.logical_xor(previous, bits[index])
        value = (value << 1) | current
        previous = current
    return value


def _decode_axis(
    images: list[np.ndarray], bit_threshold: float, scale: np.ndarray, skip: int
) -> tuple[np.ndarray, np.ndarray]:
    """1 方向分の画像列（パターンと反転パターンの対）から座標を復号する。

    ``scale`` は画素ごとの輝度の振れ幅（全白と全黒の差）です。判定を絶対値
    ではなくこの振れ幅に対する比で行うことで、対象の反射率、レンズ周辺の
    減光、Bayer 配列による色ごとの感度差を吸収します。

    ``skip`` は末尾（最も細かい側）から使わないビット数です。返り値の座標は
    投影画素単位に戻したうえで、飛ばした分のブロックの中心を指します。

    返り値は (座標, 信頼できる画素のマスク)。
    """
    bits = []
    reliable = np.ones(images[0].shape, dtype=bool)

    for index in range(0, len(images), 2):
        normal = images[index].astype(np.int32)
        inverted = images[index + 1].astype(np.int32)
        difference = normal - inverted

        bits.append(difference > 0)
        # パターンと反転パターンの差が、その画素自身の振れ幅に対して小さい
        # 場合は、どちらとも判定できません。
        reliable &= np.abs(difference) >= bit_threshold * scale

    value = _gray_to_binary(np.stack(bits))
    if skip > 0:
        # 使わなかった下位ビットの分だけ桁を戻し、そのブロックの中心を採る。
        value = (value << skip) + (1 << (skip - 1))
    return value, reliable


def decode_arrays(
    images: list[np.ndarray],
    white: np.ndarray | None,
    black: np.ndarray | None,
    projector_size: tuple[int, int],
    mask_threshold: float,
    bit_threshold: float,
    skip_fine_bits: int = 0,
) -> DecodeResult:
    """配列を直接受け取ってデコードする（ファイル入出力を伴わない中核処理）。

    images は生成時と同じ並び順、つまり横方向のパターンと反転パターンの対が
    続き、その後に縦方向の対が続く順序である必要があります。

    ``skip_fine_bits`` を 1 以上にすると、最も細かい側のビットをその数だけ
    使いません。縞幅が 1〜2 投影画素になるパターンは光学的に解像できず、
    ぼけて潰れるため、使うと画素が大量に無効になります。飛ばした分だけ
    分解能は粗くなります（1 なら 2 投影画素単位、2 なら 4 投影画素単位）。
    """
    width, height = projector_size
    column_bits, row_bits = bit_counts(width, height)
    expected = 2 * (column_bits + row_bits)
    if len(images) != expected:
        raise ValueError(
            f"パターン画像が {len(images)} 枚ですが、"
            f"{width}x{height} には {expected} 枚必要です"
        )
    if not 0 <= skip_fine_bits < min(column_bits, row_bits):
        raise ValueError(
            f"skip_fine_bits は 0 以上 {min(column_bits, row_bits) - 1} 以下です"
            f"（{skip_fine_bits} が指定されました）"
        )

    full_scale = float(np.iinfo(images[0].dtype).max)

    # 画素ごとの輝度の振れ幅。全白・全黒がなければフルスケールで代用します。
    if white is not None and black is not None:
        span = (white.astype(np.int32) - black.astype(np.int32)).astype(np.float32)
        shadow_mask = span >= mask_threshold * full_scale
        # 影の画素は振れ幅が 0 付近になり、比を取ると判定が暴れるため下限を置く。
        span = np.maximum(span, 1.0)
    else:
        span = np.full(images[0].shape, full_scale, dtype=np.float32)
        shadow_mask = np.ones(images[0].shape, dtype=bool)

    used_column = 2 * (column_bits - skip_fine_bits)
    used_row = 2 * (row_bits - skip_fine_bits)

    proj_x, reliable_x = _decode_axis(
        images[:used_column], bit_threshold, span, skip_fine_bits
    )
    proj_y, reliable_y = _decode_axis(
        images[2 * column_bits :][:used_row], bit_threshold, span, skip_fine_bits
    )

    # 復号した座標が投影解像度の外に出た画素は、判定を誤っています。
    in_range = (proj_x < width) & (proj_y < height)

    mask = shadow_mask & reliable_x & reliable_y & in_range
    proj_x = np.where(mask, proj_x, INVALID).astype(np.int32)
    proj_y = np.where(mask, proj_y, INVALID).astype(np.int32)

    return DecodeResult(
        proj_x=proj_x,
        proj_y=proj_y,
        mask=mask,
        shadow_mask=shadow_mask,
        projector_size=projector_size,
    )


def _read(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"画像を読み込めません: {path}")
    if image.ndim != 2:
        raise ValueError(
            f"{path.name} は {image.ndim} 次元です。"
            "RAW（Bayer）で撮影した 1 チャンネル画像が必要です。"
        )
    return image


def decode_capture(config: Config, name: str) -> DecodeResult:
    """data/raw/<name>/ の撮影画像を読み込んでデコードする。"""
    return decode_directory(config, config.raw_dir(name))


def decode_directory(config: Config, directory: Path) -> DecodeResult:
    """任意のディレクトリにある撮影画像を読み込んでデコードする。

    キャリブレーションでは姿勢ごとのサブディレクトリを渡します。
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"撮影データがありません: {directory}")

    width, height = config.projector.size
    column_bits, row_bits = bit_counts(width, height)
    count = 2 * (column_bits + row_bits)

    images = [_read(directory / f"pattern_{index:02d}.png") for index in range(count)]

    white_path = directory / f"{WHITE_NAME}.png"
    black_path = directory / f"{BLACK_NAME}.png"
    has_shadow_images = white_path.is_file() and black_path.is_file()
    white = _read(white_path) if has_shadow_images else None
    black = _read(black_path) if has_shadow_images else None
    if not has_shadow_images:
        print("  [警告] 全白・全黒の画像がないため、影のマスクを作れません。")

    return decode_arrays(
        images=images,
        white=white,
        black=black,
        projector_size=(width, height),
        mask_threshold=config.decode.mask_threshold,
        bit_threshold=config.decode.bit_threshold,
        skip_fine_bits=config.decode.skip_fine_bits,
    )


def bit_reliability(config: Config, name: str) -> list[tuple[int, int, float]]:
    """ビットごとの通過率を測る。

    どこまで細かい縞が解像できているかを確認し、skip_fine_bits を決めるための
    診断です。返り値は (画像の組の番号, 縞幅[投影画素], 通過率) の一覧です。
    """
    directory = config.raw_dir(name)
    width, height = config.projector.size
    column_bits, row_bits = bit_counts(width, height)

    white = _read(directory / f"{WHITE_NAME}.png")
    black = _read(directory / f"{BLACK_NAME}.png")
    # フルスケールは撮影時の dtype から取る。int32 に変換した後では
    # np.iinfo が 21 億を返してしまう。
    full_scale = float(np.iinfo(white.dtype).max)
    span = (white.astype(np.int32) - black.astype(np.int32)).astype(np.float32)
    shadow = span >= config.decode.mask_threshold * full_scale
    span = np.maximum(span, 1.0)

    report = []
    for pair in range(column_bits + row_bits):
        normal = _read(directory / f"pattern_{2 * pair:02d}.png").astype(np.int32)
        inverted = _read(directory / f"pattern_{2 * pair + 1:02d}.png").astype(np.int32)
        difference = np.abs(normal - inverted)

        bit_in_axis = pair if pair < column_bits else pair - column_bits
        total_bits = column_bits if pair < column_bits else row_bits
        stripe = 2 ** (total_bits - 1 - bit_in_axis)

        passed = (difference >= config.decode.bit_threshold * span)[shadow]
        report.append((pair, stripe, float(passed.mean())))
    return report


def _preview(coordinate: np.ndarray, maximum: int) -> np.ndarray:
    """座標マップを目視確認用のカラー画像にする。

    無効画素は黒のままにして、有効範囲だけに色を割り当てます。滑らかな
    グラデーションになっていれば正しく復号できています。
    """
    normalized = np.zeros(coordinate.shape, dtype=np.uint8)
    valid = coordinate != INVALID
    if valid.any():
        scaled = coordinate[valid].astype(np.float32) / max(maximum - 1, 1)
        normalized[valid] = np.clip(scaled * 255.0, 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
    colored[~valid] = 0
    return colored


def save(result: DecodeResult, directory: Path, source: str) -> None:
    """デコード結果を保存する。

    数値データは .npy、目視確認用のプレビューは .png で出します。
    """
    directory.mkdir(parents=True, exist_ok=True)
    width, height = result.projector_size

    np.save(directory / "proj_x.npy", result.proj_x)
    np.save(directory / "proj_y.npy", result.proj_y)

    cv2.imwrite(str(directory / "mask.png"), result.mask.astype(np.uint8) * 255)
    cv2.imwrite(
        str(directory / "shadow_mask.png"), result.shadow_mask.astype(np.uint8) * 255
    )
    cv2.imwrite(str(directory / "preview_x.png"), _preview(result.proj_x, width))
    cv2.imwrite(str(directory / "preview_y.png"), _preview(result.proj_y, height))

    metadata = {
        "decoded_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "camera_height": int(result.shape[0]),
        "camera_width": int(result.shape[1]),
        "projector_width": width,
        "projector_height": height,
        "valid_pixels": int(result.mask.sum()),
        "valid_ratio": round(result.valid_ratio, 4),
    }
    (directory / "decode.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
