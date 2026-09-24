"""キャリブレーション用に、チェッカーボードを姿勢を変えながら撮影する。

    uv run --no-sync python scripts/04_capture_calibration.py <実験名>

1 姿勢につき 2 段階で撮影します。

1. **部屋の照明を点けて 1 枚**（プロジェクタは黒を表示）
   チェッカーボードの交点を検出するための画像です。光沢のあるボードに
   プロジェクタの光を当てると、微細な鏡面反射で白マスと黒マスの区別が
   つかなくなります。拡散光である部屋の照明ならこれを避けられます。
   board.png として保存します。

2. **部屋の照明を消してパターン一式**（暗室）
   グレイコードを投影し、交点がプロジェクタのどの画素に対応するかを
   求めるための画像です。

交点の検出は 1 の直後に行うので、失敗しても数秒で分かります。パターン一式の
撮影に 1 分近くかけてから失敗に気づく、ということはありません。失敗した画像は
data/raw/<実験名>/failed/ に残るので、後から確認できます。

撮影のコツ:

- ボードは平らな板に貼り、たわませないこと
- 姿勢ごとに傾き・距離・画面内の位置を変えること（同じような姿勢ばかりだと
  精度が出ません）
- ボード全体がカメラの画面内に収まっていること
- カメラとプロジェクタは最後まで動かさないこと（両者の位置関係を求めるため）

途中で終了した場合、同じ実験名で再実行すると続きの姿勢から再開します。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from slr import calibration, capture, cli, patterns
from slr.camera import Camera
from slr.config import Config
from slr.patterns import BLACK_NAME
from slr.projector import Projector

# 交点検出用（部屋の照明で撮る）画像のファイル名。
BOARD_NAME = "board"


def survey_poses(
    config: Config, name: str, expected: list[str]
) -> tuple[list[Path], list[Path]]:
    """撮影済みの姿勢を、完全なものと不完全なものに分けて返す。

    ディレクトリの数だけを数えると、途中で中断した姿勢も「撮影済み」と
    見なしてしまい、二度と埋まらないまま残ります。必要な画像がすべて
    揃っているかを実際に確認します。
    """
    directory = config.raw_dir(name)
    if not directory.is_dir():
        return [], []

    complete, incomplete = [], []
    for pose_dir in sorted(path for path in directory.glob("pose_*") if path.is_dir()):
        missing = [
            filename
            for filename in expected
            if not (pose_dir / f"{filename}.png").is_file()
        ]
        (incomplete if missing else complete).append(pose_dir)
    return complete, incomplete


def next_pose_index(pose_dirs: list[Path]) -> int:
    """次に使う姿勢番号。欠番があっても既存を上書きしないようにする。"""
    numbers = []
    for pose_dir in pose_dirs:
        suffix = pose_dir.name.removeprefix("pose_")
        if suffix.isdigit():
            numbers.append(int(suffix))
    return max(numbers, default=0) + 1


def brightness(image: np.ndarray) -> tuple[int, float]:
    """画像の明るさの指標。(上位0.5%点, 飽和画素の割合) を返す。"""
    full_scale = np.iinfo(image.dtype).max
    peak = int(np.percentile(image, 99.5))
    saturated = float((image >= full_scale * 0.99).mean())
    return peak, saturated


def suggest_exposure(image: np.ndarray, exposure_us: float) -> float:
    """明るさの実測から、次に試す露光時間を決める。

    上位 0.5% 点がフルスケールの 60% あたりに来るように調整します。飽和して
    いる場合は、その比では下げ足りないので確実に短くします。1 回の変更幅は
    8 倍までに制限し、行き過ぎて何度も往復しないようにします。
    """
    full_scale = np.iinfo(image.dtype).max
    peak, saturated = brightness(image)

    if saturated > 0.02:
        factor = 0.4
    else:
        factor = (full_scale * 0.6) / max(peak, 1)

    factor = min(max(factor, 1.0 / 8.0), 8.0)
    return exposure_us * factor


def capture_board(
    camera: Camera,
    config: Config,
    exposure_us: float,
    board_size: tuple[int, int],
    attempts: int,
) -> tuple[np.ndarray, np.ndarray | None, float]:
    """交点が検出できるまで、露光を調整しながら撮り直す。

    返り値は (最後に撮った画像, 交点 or None, そのときの露光時間)。交点が
    見つかった露光時間を呼び出し側が引き継げば、次の姿勢からは一発で撮れます。

    明るさそのものではなく「交点を検出できたか」を成功の判定に使います。
    暗くてもコントラストがあれば検出できるためです。
    """
    image = np.zeros((1, 1), dtype=np.uint16)
    for attempt in range(1, attempts + 1):
        actual = camera.set_exposure(exposure_us)
        time.sleep(config.capture.warmup_sec)
        image = camera.grab()

        peak, saturated = brightness(image)
        corners = calibration.detect_corners(image, board_size)
        status = f"交点 {len(corners)} 点" if corners is not None else "検出できず"
        print(
            f"    [{attempt}/{attempts}] 露光 {actual:6.0f} us"
            f" / 上位0.5%点 {peak:5d} / 飽和 {saturated * 100:4.1f}%  -> {status}"
        )

        if corners is not None:
            return image, corners, actual

        next_exposure = suggest_exposure(image, actual)
        if attempt < attempts:
            if abs(next_exposure - actual) < actual * 0.1:
                # 露光を変えても改善しない。明るさ以外に原因がある。
                print("    露光の調整では改善しないようです。")
                break
            direction = "上げて" if next_exposure > actual else "下げて"
            print(f"    露光を {direction} 撮り直します。")
            exposure_us = next_exposure

    return image, None, exposure_us


def diagnose(
    image: np.ndarray, board_size: tuple[int, int], failed_dir: Path, attempt: int
) -> None:
    """検出に失敗した画像を保存し、どの交点数なら検出できるかを調べる。"""
    failed_dir.mkdir(parents=True, exist_ok=True)
    gray = calibration.to_display(image)
    path = failed_dir / f"attempt_{attempt:02d}.png"
    cv2.imwrite(str(path), gray)
    # RAW も残す。8bit に変換した後では、飽和や色ごとの感度差を追えないため。
    raw_path = failed_dir / f"attempt_{attempt:02d}_raw.png"
    cv2.imwrite(str(raw_path), image)
    print(f"    検出に使った画像を保存: {path}")
    print(f"    RAW も保存: {raw_path}")

    print("    どの交点数なら検出できるか調べます（数十秒）...")
    found = calibration.probe_board_size(image)
    if not found:
        print("    どの交点数でも検出できませんでした。")
        print("    保存した画像を開いて、ボード全体が写っているか確認してください。")
        return

    print(f"    検出できた交点数: {found}")
    if board_size not in found:
        best = max(found, key=lambda size: size[0] * size[1])
        print()
        print(f"    設定は {board_size[0]} x {board_size[1]} ですが、"
              f"実際は {best[0]} x {best[1]} のようです。")
        print("    config/default.toml の [calibration] を書き換えてください。")
        print(f"      columns = {best[0]}")
        print(f"      rows = {best[1]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="実験名（保存先ディレクトリ名になります）")
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument("--poses", type=int, default=12, help="撮影する姿勢の数")
    parser.add_argument(
        "--retries",
        type=int,
        default=4,
        help="交点が検出できないときに露光を変えて撮り直す回数",
    )
    parser.add_argument(
        "--ambient-exposure",
        type=float,
        default=None,
        help="交点検出用の露光時間（us）。設定ファイルの値を上書きする",
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    board_size = config.calibration.board_size
    names, pattern_paths = patterns.load(config)
    by_name = dict(zip(names, pattern_paths, strict=True))
    output_root = config.raw_dir(args.name)
    failed_dir = output_root / "failed"

    ambient_exposure = (
        args.ambient_exposure
        if args.ambient_exposure is not None
        else config.calibration.ambient_exposure_us
    )

    expected = [*names, BOARD_NAME]
    complete, incomplete = survey_poses(config, args.name, expected)

    # 中断で途中までしか撮れていない姿勢は、そのままでは使えないので削除します。
    for pose_dir in incomplete:
        count = len(list(pose_dir.glob("*.png")))
        print(f"不完全な姿勢を削除します: {pose_dir.name}（{count} / {len(expected)} 枚）")
        for path in pose_dir.iterdir():
            path.unlink()
        pose_dir.rmdir()
    if incomplete:
        print()

    done = len(complete)
    if done >= args.poses:
        print(f"すでに {done} 姿勢あります: {output_root}")
        print("姿勢を増やすには --poses を大きくしてください。")
        return 1

    per_pose = len(names) * (
        config.capture.warmup_sec + config.camera.exposure_time_us / 1.0e6
    )
    print(f"設定       : {config.source}")
    print(f"ボード     : 交点 {board_size[0]} x {board_size[1]}"
          f"、1 マス {config.calibration.square_size_mm} mm")
    print(f"保存先     : {output_root}")
    print(f"姿勢       : {done} 済み / {args.poses} 目標")
    print(f"露光       : 検出用 {ambient_exposure:.0f} us"
          f" / 投影時 {config.camera.exposure_time_us:.0f} us")
    print(f"1 姿勢あたり: 約 {per_pose:.0f} 秒")
    print()
    print("カメラとプロジェクタは最後まで動かさないでください。")
    print()

    attempt = 0
    with Camera(config) as camera, Projector(config) as projector:
        camera.start()
        pose = done
        index = next_pose_index(complete)

        while pose < args.poses:
            print(f"--- 姿勢 {pose + 1} / {args.poses} ---")
            print("  [1] ボードを置き、部屋の照明を点けて Enter（やめるなら q）: ",
                  end="", flush=True)
            if input().strip().lower() == "q":
                print("終了します。")
                break

            # プロジェクタを黒にして、部屋の照明だけで交点検出用の 1 枚を撮る。
            attempt += 1
            projector.show(by_name[BLACK_NAME])
            board_image, corners, actual = capture_board(
                camera, config, ambient_exposure, board_size, args.retries
            )

            if corners is None:
                print("    交点を検出できませんでした。パターン撮影は行いません。")
                diagnose(board_image, board_size, failed_dir, attempt)
                camera.set_exposure(config.camera.exposure_time_us)
                print()
                continue

            # うまくいった露光を次の姿勢に引き継ぐ。
            ambient_exposure = actual

            # ここから暗室でのパターン撮影。露光を投影用に戻す。
            print("  [2] 部屋の照明を消して Enter: ", end="", flush=True)
            input()
            camera.set_exposure(config.camera.exposure_time_us)

            pose_dir = output_root / f"pose_{index:02d}"
            pose_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(pose_dir / f"{BOARD_NAME}.png"), board_image)

            try:
                elapsed = capture.capture_sequence(
                    config, camera, projector, names, pattern_paths, pose_dir
                )
            except capture.CaptureAborted:
                # 途中までの画像を残すと、後の実行で「撮影済み」と誤認されます。
                for path in pose_dir.iterdir():
                    path.unlink()
                pose_dir.rmdir()
                print(f"    中断しました。{pose_dir.name} は削除しました。")
                raise
            capture.save_metadata(
                pose_dir,
                config,
                camera,
                names,
                elapsed,
                extra={
                    "board_columns": board_size[0],
                    "board_rows": board_size[1],
                    "square_size_mm": config.calibration.square_size_mm,
                    "ambient_exposure_us": actual,
                    "detected_corners": len(corners),
                },
            )
            pose += 1
            index += 1
            print(f"    撮影完了（{elapsed:.0f} 秒）")
            print()

        camera.stop()

    total = len(survey_poses(config, args.name, expected)[0])
    print(f"完了: {total} 姿勢を撮影しました。")
    if total < config.calibration.min_poses:
        print(
            f"  [警告] キャリブレーションには最低 {config.calibration.min_poses} 姿勢"
            "必要です。同じ実験名で再実行すると続きから撮影できます。"
        )
    else:
        print(f"次: uv run --no-sync python scripts/05_calibrate.py {args.name}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
