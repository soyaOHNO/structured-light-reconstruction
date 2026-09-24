"""キャリブレーションのうち、実機なしで確認できる部分のテスト。

    uv run --no-sync python tests/test_calibration.py

合成したチェッカーボード画像で交点検出を確認し、既知の射影変換を与えた
デコード結果から交点のプロジェクタ座標が正しく求まるかを確認します。
"""

from __future__ import annotations

import sys
from dataclasses import replace

import cv2
import numpy as np

from slr import calibration
from slr.config import Config
from slr.decode import DecodeResult


def make_board(columns: int, rows: int, square: int = 60, margin: int = 60) -> np.ndarray:
    """交点が columns x rows になるチェッカーボード画像を作る。

    交点が columns x rows なら、マスは (columns + 1) x (rows + 1) です。
    検出には周囲の余白が必要なので margin を付けます。
    """
    squares_x, squares_y = columns + 1, rows + 1
    board = np.zeros((squares_y * square, squares_x * square), dtype=np.uint8)
    for row in range(squares_y):
        for column in range(squares_x):
            if (row + column) % 2 == 0:
                board[
                    row * square : (row + 1) * square,
                    column * square : (column + 1) * square,
                ] = 255
    return cv2.copyMakeBorder(
        board, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=255
    )


def detection_finds_all_corners(columns: int, rows: int) -> np.ndarray:
    board = make_board(columns, rows)
    corners = calibration.detect_corners(board, (columns, rows))
    assert corners is not None, f"{columns}x{rows}: 交点を検出できませんでした"
    assert len(corners) == columns * rows, (
        f"{columns}x{rows}: 交点が {len(corners)} 点しか見つかりません"
        f"（{columns * rows} 点あるはずです）"
    )
    print(f"  {columns} x {rows}: OK（{len(corners)} 点）")
    return corners


def detection_rejects_wrong_size() -> None:
    """実際と違う交点数を指定したら、黙って別のものを返さずに失敗すること。"""
    board = make_board(9, 6)
    assert calibration.detect_corners(board, (8, 5)) is None, (
        "9x6 のボードが 8x5 として検出されました"
    )
    print("  誤った交点数を拒否: OK")


def probe_finds_the_true_size() -> None:
    """--probe がボードの実際の交点数を当てられること。"""
    board = make_board(9, 6)
    found = calibration.probe_board_size(board, maximum=10)
    assert (9, 6) in found, f"9x6 が見つかりません（見つかったもの: {found}）"
    print(f"  総当たり検出: OK（{found} を検出、最大が正解）")


def projector_corners_recovers_known_transform() -> None:
    """既知の射影変換を与えたとき、交点が正しく移ること。

    カメラ座標 -> プロジェクタ座標を単純な拡大縮小＋平行移動とし、
    デコード結果をその変換で作ります。交点をその変換で移した結果と、
    projector_corners の出力が一致するはずです。
    """
    height, width = 400, 600
    scale_x, scale_y = 0.5, 0.5
    offset_x, offset_y = 120.0, 80.0

    columns_grid, rows_grid = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
    )
    proj_x = np.round(columns_grid * scale_x + offset_x).astype(np.int32)
    proj_y = np.round(rows_grid * scale_y + offset_y).astype(np.int32)
    mask = np.ones((height, width), dtype=bool)

    decoded = DecodeResult(
        proj_x=proj_x,
        proj_y=proj_y,
        mask=mask,
        shadow_mask=mask,
        projector_size=(1920, 1080),
    )

    camera_corners = np.array(
        [[[150.5, 120.25]], [[300.0, 200.0]], [[450.75, 310.5]]], dtype=np.float32
    )
    mapped = calibration.projector_corners(decoded, camera_corners, window=30)
    assert mapped is not None, "プロジェクタ座標を求められませんでした"

    expected = camera_corners.reshape(-1, 2) * [scale_x, scale_y] + [offset_x, offset_y]
    error = np.abs(mapped.reshape(-1, 2) - expected).max()
    assert error < 0.5, f"誤差が {error:.3f} 画素あります"
    print(f"  既知の変換を復元: OK（最大誤差 {error:.3f} 画素）")


def projector_corners_rejects_empty_region() -> None:
    """デコードできていない場所では、推測せずに諦めること。"""
    height, width = 400, 600
    decoded = DecodeResult(
        proj_x=np.zeros((height, width), dtype=np.int32),
        proj_y=np.zeros((height, width), dtype=np.int32),
        mask=np.zeros((height, width), dtype=bool),
        shadow_mask=np.zeros((height, width), dtype=bool),
        projector_size=(1920, 1080),
    )
    corners = np.array([[[300.0, 200.0]]], dtype=np.float32)
    assert calibration.projector_corners(decoded, corners, window=30) is None, (
        "有効画素が 0 なのに座標を返しました"
    )
    print("  有効画素なしを拒否: OK")


def calibrate_requires_enough_poses() -> None:
    config = Config.load()
    strict = replace(
        config, calibration=replace(config.calibration, min_poses=8)
    )
    try:
        calibration.calibrate(strict, [], [], [], (1920, 1200), [])
    except ValueError as error:
        print(f"  姿勢数の不足を検出: OK（{error}）")
        return
    raise AssertionError("姿勢が 0 件なのに例外が出ませんでした")


def main() -> int:
    config = Config.load()
    columns, rows = config.calibration.board_size
    print(f"設定のボード: 交点 {columns} x {rows}\n")

    print("交点検出:")
    detection_finds_all_corners(columns, rows)
    detection_finds_all_corners(7, 5)
    detection_rejects_wrong_size()
    probe_finds_the_true_size()

    print("\nプロジェクタ座標への変換:")
    projector_corners_recovers_known_transform()
    projector_corners_rejects_empty_region()

    print("\n異常系:")
    calibrate_requires_enough_poses()

    print("\nすべて成功しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
