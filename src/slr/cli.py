"""スクリプト共通の実行ラッパー。

設定ミスや機材の未接続は実験中に日常的に起きるので、トレースバックではなく
一行のエラーメッセージで返します。想定外の例外はそのまま送出して、
デバッグに必要な情報を失わないようにします。
"""

from __future__ import annotations

import sys
from collections.abc import Callable


def run(main: Callable[[], int]) -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("\n中断しました。", file=sys.stderr)
        return 130
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
