# structured-light-reconstruction

構造化光（structured light）を用いた三次元形状復元のプロジェクトです。

## 1. 概要

プロジェクタで既知のパターンを対象物へ投影し、それをカメラで撮影します。撮影画像からプロジェクタ画素とカメラ画素の対応を求め、キャリブレーション済みのカメラ・プロジェクタ間の三角測量によって対象物の三次元形状を復元することを目的とします。

処理の流れは次を想定しています。

```
パターン生成 → 投影・撮影（同期） → デコード（対応点抽出） → キャリブレーション → 三角測量 → 点群出力
```

### 現在の進捗

**ハードウェアのセットアップと動作確認までが完了しています。** 復元アルゴリズム本体（パターン生成・デコード・キャリブレーション・三角測量）はこれからの実装です。

- 完了: Spinnaker SDK / PySpin の導入、Python からのカメラ認識・静止画撮影、プロジェクタへの全画面パターン表示
- 未着手: 計測手順（[measurement/measurement.md](measurement/measurement.md) は空ファイル）、および `src/` 以下の本体実装（現状は `uv init` が生成したひな形のみ）

### 動作確認環境

| 項目 | 構成 |
| --- | --- |
| OS | Windows 64bit（Windows 11） |
| カメラ | FLIR Blackfly S BFS-U3-23S3C（USB 3 接続） |
| プロジェクタ | BenQ・HDMI 接続、800 × 600 / 60 Hz / 拡大率 100% |
| Spinnaker SDK / SpinView | 4.4.0.246（x64） |
| PySpin | spinnaker_python 4.4.0.246（cp312 / win_amd64） |
| Python | CPython 3.12（`.python-version` は 3.12） |
| パッケージ管理 | uv 0.12.13 |

詳細な手順は [setup/setup.md](setup/setup.md) を参照してください。

## 2. TODO

### 計測フェーズ（次にやること）

- [ ] `measurement/measurement.md` の執筆（撮影手順書。現在は空ファイル）
- [ ] 露光時間・ゲイン・ピント・絞りの調整手順の確立と、計測用の画素形式の決定
- [ ] グレイコードパターン（および必要なら位相シフトパターン）の生成
- [ ] 投影と撮影を同期させる自動撮影スクリプト（パターン切り替え → 待機 → 撮影のループ）
- [ ] 撮影画像セットの保存規約（ディレクトリ名・ファイル名・メタデータ）の決定

### 復元フェーズ

- [ ] デコード処理（撮影画像からプロジェクタ座標を復元し、カメラ画素との対応を作る）
- [ ] 全白・全黒画像を用いた有効画素マスク（影・照り返し・飽和の除去）
- [ ] カメラの内部パラメータ・レンズ歪みのキャリブレーション
- [ ] プロジェクタの内部パラメータおよびカメラ・プロジェクタ間の外部パラメータのキャリブレーション
- [ ] 三角測量による点群生成
- [ ] 点群の出力（PLY 等）と可視化
- [ ] 平面・球など既知形状を用いた精度評価

### 整備

- [ ] `src/structured_light_reconstruction/` に本体モジュールを実装（現状 `main()` のひな形のみ）
- [ ] `pyproject.toml` の `description` を記入し、依存パッケージ（numpy・opencv-python 等）を追加
- [ ] PySpin を `uv sync` で消さずに扱う方法の整理（現状は wheel を `uv pip install` で別途導入）
- [ ] Git リポジトリの初期化（現時点では未初期化。`.gitignore` は用意済み）
- [ ] 自動テストの整備

## 3. ディレクトリ構成

```text
structured-light-reconstruction/
├── README.md                  このファイル
├── pyproject.toml             プロジェクト定義（uv / uv_build）
├── uv.lock                    依存の固定ファイル
├── .python-version            使用する Python のバージョン（3.12）
├── .gitignore                 Git 除外設定
│
├── src/
│   └── structured_light_reconstruction/
│       └── __init__.py        パッケージ本体（現状はひな形）
│
├── setup/                     セットアップ手順と動作確認スクリプト
│   ├── setup.md               Windows でのカメラ・プロジェクタ構築手順書
│   ├── check_camera.py        カメラ認識の確認
│   ├── capture_one.py         静止画 1 枚の撮影・保存
│   ├── projector_test.py      プロジェクタへの全画面表示（白／黒／縞）
│   ├── captures/              動作確認で撮影した画像（Git 管理外）
│   ├── installers/            Spinnaker SDK の EXE と PySpin の ZIP（Git 管理外・約 600 MB）
│   └── vendor/                PySpin ZIP の展開先。wheel と公式ドキュメント（Git 管理外）
│
└── measurement/               計測フェーズ
    ├── measurement.md         計測手順書（未執筆・空ファイル）
    └── captures/
        └── manual_test/       手動での投影・撮影テスト画像
            ├── white.png
            ├── black.png
            └── stripes.png
```

`setup/installers/`、`setup/vendor/`、`setup/captures/`、`.venv/` は `.gitignore` で除外しています。別 PC で環境を作り直す場合は、[setup/setup.md](setup/setup.md) の手順 5 に従って配布物を再取得してください。

## 4. 各ファイルの役割

### セットアップ・動作確認

| ファイル | 役割 |
| --- | --- |
| [setup/setup.md](setup/setup.md) | Windows 上でのカメラ・プロジェクタ構築手順書。uv によるプロジェクト作成、Spinnaker SDK のインストール、SpinView での確認、PySpin の導入、プロジェクタの 2 画面設定、環境の再作成手順、完了チェックリストまでを網羅しています。 |
| [setup/check_camera.py](setup/check_camera.py) | PySpin で `System` を取得して接続カメラを列挙し、台数・型番（`DeviceModelName`）・シリアル番号（`DeviceSerialNumber`）を表示します。カメラが認識できているかの最小確認用です。 |
| [setup/capture_one.py](setup/capture_one.py) | カメラを初期化し、トリガ off・連続取得モードで 1 フレーム取得して `setup/captures/` へ日時付き PNG（`capture_YYYYmmdd_HHMMSS_ffffff.png`）を保存します。`ImageProcessor` で HQ Linear のデモザイクを行い RGB8 へ変換します。この RGB8 変換は表示確認用で、計測用の画素形式は別途決める前提です。`finally` で取得停止・`DeInit`・`ReleaseInstance` まで必ず解放します。 |
| [setup/projector_test.py](setup/projector_test.py) | Tkinter で枠なし全画面ウィンドウをプロジェクタ側ディスプレイに出し、パターンを表示します。`SetProcessDpiAwareness(2)` で拡大率によるずれを防ぎ、`GetSystemMetrics(0)`（メイン画面の幅）を X オフセットにして「プロジェクタがメイン画面の右隣・上端揃え」という配置を前提に表示位置を決めています。キー操作は W = 全白、B = 全黒、S = 縦縞（幅 40 px）、Esc = 終了。解像度は `WIDTH = 800` / `HEIGHT = 600` に固定です。 |

### 計測

| ファイル | 役割 |
| --- | --- |
| [measurement/measurement.md](measurement/measurement.md) | 計測手順書。露光・ピント調整、グレイコード生成、自動撮影、キャリブレーションを扱う予定ですが、**現在は空ファイル**です。 |
| `measurement/captures/manual_test/` | `projector_test.py` の白・黒・縞をカメラで手動撮影したテスト画像です。 |

### プロジェクト管理

| ファイル | 役割 |
| --- | --- |
| [pyproject.toml](pyproject.toml) | プロジェクト定義。`requires-python = ">=3.12"`、ビルドバックエンドは `uv_build`、コンソールスクリプト `structured-light-reconstruction` を `structured_light_reconstruction:main` に割り当てています。`dependencies` は現在空です。 |
| [uv.lock](uv.lock) | uv の依存固定ファイル。現状は本パッケージ自身（editable）のみです。 |
| [src/structured_light_reconstruction/\_\_init\_\_.py](src/structured_light_reconstruction/__init__.py) | パッケージのエントリポイント。現状は `uv init` が生成した `main()` のひな形です。 |
| [.gitignore](.gitignore) | `.venv/`、`__pycache__/`、`setup/installers/`、`setup/vendor/`、`setup/captures/` を除外します。 |

## 5. セットアップと実行

前提として Spinnaker SDK（4.4.0.246 x64）がインストール済みで、PySpin の wheel が `setup/vendor/` に展開されている必要があります。初回構築は [setup/setup.md](setup/setup.md) を参照してください。

```powershell
# 仮想環境の作成と同期
uv sync

# PySpin の導入（pyproject.toml / uv.lock には登録されないため毎回手動）
uv pip install ".\setup\vendor\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl"

# 動作確認
uv run --no-sync python setup/check_camera.py      # カメラ認識
uv run --no-sync python setup/capture_one.py       # 1 枚撮影
uv run --no-sync python setup/projector_test.py    # 投影テスト（W/B/S/Esc）
```

PySpin はロックファイルの管理外なので、`uv sync` や仮想環境の再作成で消えることがあります。その場合は wheel のインストールをやり直してください。スクリプトの実行は `--no-sync` を付けて、`uv` による自動同期で PySpin が削除されるのを防ぎます。

> **注意:** カメラは SpinView と Python から同時に開けません。Python スクリプトを実行する前に SpinView を終了してください。

## 6. 参考資料

### 公式ドキュメント・SDK

- [Teledyne FLIR Spinnaker SDK](https://www.flir.com/products/spinnaker-sdk/) — SDK 本体と PySpin の配布元
- `setup/vendor/.../docs/Spinnaker-Python-Programmer-Guide.pdf` — PySpin のプログラミングガイド（ローカル）
- `setup/vendor/.../docs/site/api/pyspin_ref/` — PySpin の API リファレンス（ローカル HTML）
- `setup/vendor/.../Examples/` — PySpin の公式サンプルコード（ローカル）
- [uv ドキュメント](https://docs.astral.sh/uv/) — パッケージ・環境管理
- [OpenCV: Camera Calibration and 3D Reconstruction](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html) — キャリブレーションと三角測量
- [OpenCV: Structured Light (`cv::structured_light`)](https://docs.opencv.org/4.x/d1/d90/namespacecv_1_1structured__light.html) — グレイコードパターンの生成・デコード

### 技術資料

- S. Inokuchi, K. Sato, F. Matsuda, "Range imaging system for 3-D object recognition," ICPR 1984 — グレイコード法の基礎
- D. Scharstein and R. Szeliski, "High-accuracy stereo depth maps using structured light," CVPR 2003 — 構造化光による高精度ステレオ
- J. Salvi, S. Fernandez, T. Pribanic, X. Llado, "A state of the art in structured light patterns for surface profilometry," Pattern Recognition 43(8), 2010 — パターン方式の網羅的なサーベイ
- D. Moreno and G. Taubin, "Simple, Accurate, and Robust Projector-Camera Calibration," 3DIMPVT 2012 — プロジェクタ・カメラのキャリブレーション手法
- S. Zhang, "High-speed 3D shape measurement with structured light methods: A review," Optics and Lasers in Engineering 106, 2018 — 位相シフト法を含む近年の総説
