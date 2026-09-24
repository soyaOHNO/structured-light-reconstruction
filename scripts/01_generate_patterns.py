"""投影するグレイコードパターンを生成して data/patterns/<解像度>/ に保存する。

    uv run --no-sync python scripts/01_generate_patterns.py

解像度は config/default.toml の [projector] から読みます。プロジェクタを
変更したときは、設定を直してからこのスクリプトを実行し直してください。
"""

from __future__ import annotations

import argparse
import sys

from slr import cli, patterns
from slr.config import Config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存のパターンを上書きする",
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    directory = config.pattern_dir

    if directory.exists() and any(directory.iterdir()) and not args.force:
        print(f"すでにパターンがあります: {directory}")
        print("上書きするには --force を付けてください。")
        return 1

    width, height = config.projector.size
    print(f"設定       : {config.source}")
    print(f"投影解像度 : {width} x {height}")

    pattern_set = patterns.build(config)
    print(
        f"生成枚数   : {len(pattern_set)} 枚"
        f"（グレイコード {pattern_set.graycode_count} 枚"
        f" + マスク用 {len(pattern_set) - pattern_set.graycode_count} 枚）"
    )

    manifest_path = patterns.save(pattern_set, directory)
    print(f"保存先     : {directory}")
    print(f"manifest   : {manifest_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
