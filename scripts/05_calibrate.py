"""撮影したチェッカーボードから、カメラとプロジェクタをキャリブレーションする。

    uv run --no-sync python scripts/05_calibrate.py <実験名>

各姿勢についてグレイコードをデコードし、チェッカーボードの交点がプロジェクタの
どの画素に対応するかを求めます。その対応からカメラ・プロジェクタそれぞれの内部
パラメータと、両者の相対姿勢を推定して data/results/<実験名>/calibration.json
に保存します。

ボードの交点数が分からない場合は、--probe で実測できます。

    uv run --no-sync python scripts/05_calibrate.py <実験名> --probe
"""

from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np

from slr import calibration, cli, decode, patterns
from slr.config import Config
from slr.patterns import WHITE_NAME

# 交点検出用の画像。部屋の照明で撮った board.png を優先し、無ければ投影時の
# 全白画像を使う（board.png を撮るようになる前のデータとの互換のため）。
BOARD_NAME = "board"


def load_detection_image(pose_dir):
    """交点検出に使う画像を読み込む。返り値は (画像, 由来)。"""
    board_path = pose_dir / f"{BOARD_NAME}.png"
    if board_path.is_file():
        return cv2.imread(str(board_path), cv2.IMREAD_UNCHANGED), "部屋の照明"
    white_path = pose_dir / f"{WHITE_NAME}.png"
    if white_path.is_file():
        return cv2.imread(str(white_path), cv2.IMREAD_UNCHANGED), "投影の全白"
    return None, "なし"


def missing_images(pose_dir, expected: list[str]) -> list[str]:
    """その姿勢に足りない画像のファイル名。"""
    return [
        filename
        for filename in expected
        if not (pose_dir / f"{filename}.png").is_file()
    ]


def pose_directories(config: Config, name: str) -> list:
    root = config.raw_dir(name)
    if not root.is_dir():
        raise FileNotFoundError(f"撮影データがありません: {root}")
    poses = sorted(path for path in root.glob("pose_*") if path.is_dir())
    if not poses:
        raise FileNotFoundError(
            f"{root} に pose_* のディレクトリがありません。"
            "先に scripts/04_capture_calibration.py を実行してください。"
        )
    return poses


def probe(config: Config, name: str) -> int:
    """最初の姿勢の画像で、検出できる交点数を総当たりで調べる。"""
    poses = pose_directories(config, name)
    white, origin = load_detection_image(poses[0])
    if white is None:
        raise FileNotFoundError(f"{poses[0]} に検出用の画像がありません")
    print(f"調査対象: {poses[0]}（{origin}）")
    print("総当たりで検出を試します（数十秒かかります）...")

    found = calibration.probe_board_size(white)
    if not found:
        print("\nどの交点数でも検出できませんでした。")
        print("ボードが画面に収まっているか、明るさが十分かを確認してください。")
        return 1

    print("\n検出できた交点数:")
    for columns, rows in found:
        print(f"  {columns} x {rows}")
    print()
    print("config/default.toml の [calibration] に設定してください。")
    print("複数見つかった場合は、最も大きいものが通常のボード全体です。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="実験名（data/raw/ 以下のディレクトリ名）")
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument(
        "--probe", action="store_true", help="検出できる交点数を総当たりで調べる"
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    if args.probe:
        return probe(config, args.name)

    board_size = config.calibration.board_size
    poses = pose_directories(config, args.name)
    template = calibration.board_object_points(config.calibration)
    pattern_names, _ = patterns.load(config)
    expected_images = list(pattern_names)

    print(f"設定       : {config.source}")
    print(f"ボード     : 交点 {board_size[0]} x {board_size[1]}"
          f"、1 マス {config.calibration.square_size_mm} mm")
    print(f"姿勢       : {len(poses)} 件")
    print()

    object_points = []
    camera_points = []
    projector_points = []
    used_names = []
    camera_size: tuple[int, int] | None = None

    for pose_dir in poses:
        print(f"  {pose_dir.name}: ", end="", flush=True)

        lacking = missing_images(pose_dir, expected_images)
        if lacking:
            print(
                f"画像が {len(lacking)} 枚足りません"
                f"（{lacking[0]} など）。飛ばします。"
            )
            continue

        detection_image, origin = load_detection_image(pose_dir)
        if detection_image is None:
            print("検出用の画像がありません。飛ばします。")
            continue
        camera_size = (detection_image.shape[1], detection_image.shape[0])

        corners = calibration.detect_corners(detection_image, board_size)
        if corners is None:
            print("交点を検出できません。飛ばします。")
            continue

        decoded = decode.decode_directory(config, pose_dir)
        mapped = calibration.projector_corners(
            decoded, corners, config.calibration.corner_window
        )
        if mapped is None:
            print("交点まわりのデコード結果が足りません。飛ばします。")
            continue

        object_points.append(template)
        camera_points.append(corners)
        projector_points.append(mapped)
        used_names.append(pose_dir.name)
        print(
            f"交点 {len(corners)} 点（{origin}）"
            f" / 有効画素 {decoded.valid_ratio * 100:.0f}%"
        )

    print()
    print(f"使用する姿勢: {len(used_names)} / {len(poses)} 件")

    if camera_size is None:
        raise RuntimeError("画像を 1 枚も読み込めませんでした")

    result = calibration.calibrate(
        config, object_points, camera_points, projector_points, camera_size, used_names
    )

    print()
    print("再投影誤差（画素、小さいほど良い。1.0 未満が目安）:")
    print(f"  カメラ      : {result.camera_error:.4f}")
    print(f"  プロジェクタ: {result.projector_error:.4f}")
    print(f"  ステレオ    : {result.stereo_error:.4f}")
    print()
    print(f"カメラ焦点距離      : fx={result.camera_matrix[0, 0]:.1f} "
          f"fy={result.camera_matrix[1, 1]:.1f}")
    print(f"プロジェクタ焦点距離: fx={result.projector_matrix[0, 0]:.1f} "
          f"fy={result.projector_matrix[1, 1]:.1f}")
    print(f"基線長（カメラ-プロジェクタ間）: {result.baseline_mm:.1f} mm")

    if max(result.camera_error, result.projector_error, result.stereo_error) > 1.0:
        print()
        print("  [警告] 再投影誤差が大きいです。次を確認してください。")
        print("         - ボードが平らで、たわんでいないか")
        print("         - 姿勢のばらつきが十分か（傾き・距離・位置）")
        print("         - 1 マスの実寸が config の値と合っているか")

    output = config.result_dir(args.name) / "calibration.json"
    calibration.save(result, output)
    print()
    print(f"保存先: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
