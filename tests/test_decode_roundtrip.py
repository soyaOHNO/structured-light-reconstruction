"""パターン生成とデコードの往復テスト。

    uv run --no-sync python tests/test_decode_roundtrip.py

生成したパターン画像を「ノイズのない完全な撮影画像」とみなしてデコードし、
復号した座標が元の画素位置と完全に一致するかを確認します。

デコード側はパターンの並び順（横方向の対が先、その後に縦方向の対。各対は
パターンとその反転。最上位ビットが先頭）を前提にしています。この前提が
崩れると結果は無意味になりますが、実写では「なんとなく歪んだ結果」として
現れて原因に気づきにくいため、ここで機械的に検証します。
"""

from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np

from slr import decode, patterns
from slr.config import Config


def roundtrip(config: Config) -> None:
    width, height = config.projector.size
    pattern_set = patterns.build(config)

    names = pattern_set.names
    images = pattern_set.images
    graycode_images = images[: pattern_set.graycode_count]
    white = images[names.index(patterns.WHITE_NAME)]
    black = images[names.index(patterns.BLACK_NAME)]

    result = decode.decode_arrays(
        images=graycode_images,
        white=white,
        black=black,
        projector_size=(width, height),
        mask_threshold=config.decode.mask_threshold,
        bit_threshold=config.decode.bit_threshold,
    )

    expected_x = np.tile(np.arange(width, dtype=np.int32), (height, 1))
    expected_y = np.tile(np.arange(height, dtype=np.int32).reshape(-1, 1), (1, width))

    assert result.mask.all(), (
        f"{width}x{height}: 無効画素が {int((~result.mask).sum())} 個あります"
        "（完全な入力なので全画素が有効になるはずです）"
    )

    mismatched_x = int((result.proj_x != expected_x).sum())
    mismatched_y = int((result.proj_y != expected_y).sum())
    assert mismatched_x == 0, f"{width}x{height}: 横座標が {mismatched_x} 画素ずれています"
    assert mismatched_y == 0, f"{width}x{height}: 縦座標が {mismatched_y} 画素ずれています"

    column_bits, row_bits = decode.bit_counts(width, height)
    print(
        f"  {width} x {height}: OK"
        f"（{column_bits}+{row_bits} bit, {len(graycode_images)} 枚, 全画素一致）"
    )


def roundtrip_with_skipped_bits(config: Config, skip: int) -> None:
    """細かいビットを飛ばしたとき、座標がブロックの中心を指すこと。

    skip=2 なら 4 投影画素ごとのブロックになり、復号結果はその中心
    （0,1,2,3 -> 2 / 4,5,6,7 -> 6）になるはずです。
    """
    width, height = config.projector.size
    pattern_set = patterns.build(config)
    names = pattern_set.names

    result = decode.decode_arrays(
        images=pattern_set.images[: pattern_set.graycode_count],
        white=pattern_set.images[names.index(patterns.WHITE_NAME)],
        black=pattern_set.images[names.index(patterns.BLACK_NAME)],
        projector_size=(width, height),
        mask_threshold=config.decode.mask_threshold,
        bit_threshold=config.decode.bit_threshold,
        skip_fine_bits=skip,
    )

    block = 1 << skip
    columns = np.arange(width, dtype=np.int32)
    rows = np.arange(height, dtype=np.int32)
    expected_x = np.tile((columns // block) * block + block // 2, (height, 1))
    expected_y = np.tile(((rows // block) * block + block // 2).reshape(-1, 1), (1, width))

    valid = result.mask
    mismatched_x = int((result.proj_x[valid] != expected_x[valid]).sum())
    mismatched_y = int((result.proj_y[valid] != expected_y[valid]).sum())
    assert mismatched_x == 0, f"skip={skip}: 横座標が {mismatched_x} 画素ずれています"
    assert mismatched_y == 0, f"skip={skip}: 縦座標が {mismatched_y} 画素ずれています"
    print(
        f"  {width} x {height} skip={skip}: OK"
        f"（{block} 投影画素単位, 有効 {result.valid_ratio * 100:.1f}%）"
    )


def wrong_image_count_is_rejected(config: Config) -> None:
    """枚数が足りない画像列を渡したら、黙って進まずに止まること。"""
    pattern_set = patterns.build(config)
    truncated = pattern_set.images[: pattern_set.graycode_count - 2]
    try:
        decode.decode_arrays(
            images=truncated,
            white=None,
            black=None,
            projector_size=config.projector.size,
            mask_threshold=config.decode.mask_threshold,
            bit_threshold=config.decode.bit_threshold,
        )
    except ValueError as error:
        print(f"  枚数不足を検出: OK（{error}）")
        return
    raise AssertionError("枚数が足りないのに例外が出ませんでした")


def main() -> int:
    config = Config.load()
    print(f"設定: {config.source}\n")

    print("往復テスト:")
    # 小さい解像度で素早く確認してから、実際の投影解像度で確認します。
    small = replace(config, projector=replace(config.projector, width=64, height=48))
    roundtrip(small)

    # 2 のべき乗でない解像度では、符号化されない余りの領域が出ます。
    odd = replace(config, projector=replace(config.projector, width=100, height=80))
    roundtrip(odd)

    roundtrip(config)

    print("\nビットを飛ばした場合:")
    roundtrip_with_skipped_bits(small, skip=1)
    roundtrip_with_skipped_bits(small, skip=2)
    roundtrip_with_skipped_bits(config, skip=2)

    print("\n異常系:")
    wrong_image_count_is_rejected(small)

    print("\nすべて成功しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
