# structured-light-reconstruction

プロジェクタとカメラを用いた、構造化光による三次元形状復元の研究プロジェクトです。

対象物にパターンを投影して撮影し、カメラ画素とプロジェクタ画素の対応を求めます。キャリブレーションで得たパラメータと対応点を使い、三角測量によって三次元形状を復元することを目指します。

## 現在の状態

**パターン生成から三次元点群の出力、精度評価まで、一連の処理が実機で通りました。** 背景の壁に平面を当てはめた残差は RMS 0.380 mm（計測距離約 600 mm、相対 0.06%）です。手順と実測値は [docs/measurement.md](docs/measurement.md) と [docs/reconstruction.md](docs/reconstruction.md) に記録しています。

| 項目 | 状態 |
| --- | --- |
| Windows・uv・Python の環境構築 | 完了 |
| Spinnaker SDK・PySpin の導入 | 完了 |
| SpinView での映像表示・撮影 | 確認済み |
| Python からのカメラ認識・静止画保存 | 確認済み |
| プロジェクタへの白・黒・縞パターン表示 | 確認済み |
| 白・黒・縞パターンの手動撮影 | 確認済み |
| 暗室への機材設置 | 完了 |
| グレーコードパターンの生成 | 実装済み（1920 × 1080 用に 46 枚を生成済み） |
| 投影・撮影の自動化 | 実装済み・実写で確認済み（46 枚を 57.5 秒） |
| デコード（対応点の抽出） | 実装済み・実写で確認済み（有効画素 40%、約 92 万点） |
| カメラ・プロジェクタのキャリブレーション | 実装済み・実写で確認済み（再投影誤差 0.20 / 0.24 / 0.46 画素） |
| 三次元復元（三角測量・点群出力） | 実装済み・実写で確認済み（435,491 点） |
| 精度評価 | 実装済み・実写で確認済み（平面の残差 RMS 0.380 mm）。球によるスケール確認と、距離を変えた評価はこれから |
| 位相シフト法の併用 | 未着手。計画は [docs/phase-shift-plan.md](docs/phase-shift-plan.md) |

精度評価は背景の壁 1 面で確認しただけです。既知形状を使った系統的な評価はこれからです。

## 使用環境

| 項目 | 構成 |
| --- | --- |
| OS | Windows 11（64bit） |
| カメラ | FLIR Blackfly S BFS-U3-23S3C、USB 3 接続 |
| レンズ | TAMRON、焦点距離 16 mm、F/2.0 |
| プロジェクタ | BenQ（型番未確認）、HDMI 接続 |
| 投影設定 | 1920 × 1080、拡大率 100%、拡張表示、台形補正なし |
| Spinnaker SDK / SpinView | 4.4.0.246（x64） |
| PySpin | spinnaker_python 4.4.0.246（cp312 / win_amd64） |
| Python | CPython 3.12.14 |
| 環境・パッケージ管理 | uv 0.12.13、プロジェクト内の `.venv` |

露光時間・ゲイン・絞り・ピントなどの計測条件は、暗室での配置と投影状態を確認しながら決めます。これまでの動作確認で使った値は、計測用の確定値にはしません。

## 手順書とファイルの役割

| 場所 | 役割 |
| --- | --- |
| [setup/setup.md](setup/setup.md) | 環境構築から、カメラで撮影しプロジェクタへ表示できるまでの手順 |
| `setup/check_camera.py` | カメラの認識確認 |
| `setup/capture_one.py` | 静止画 1 枚の撮影・保存 |
| `setup/projector_test.py` | 白・黒・縞パターンの投影確認 |
| `setup/installers/` | SDK インストーラと PySpin の配布 ZIP |
| `setup/vendor/` | PySpin 配布 ZIP の展開先（wheel、公式資料、サンプル） |
| `setup/captures/` | セットアップ時の撮影画像 |
| [docs/measurement.md](docs/measurement.md) | 暗室での計測手順。機材配置、光学条件の決め方、校正、撮影 |
| [docs/reconstruction.md](docs/reconstruction.md) | 撮影後の処理手順。デコード、三角測量、精度評価 |
| [docs/code.md](docs/code.md) | コードの読み方。各モジュールの役割と設計の理由 |
| [docs/phase-shift-plan.md](docs/phase-shift-plan.md) | **次に実装する内容**。位相シフト法の導入計画（未着手） |
| [config/default.toml](config/default.toml) | 投影解像度、露光・ゲイン・ガンマ・ホワイトバランス、待機時間、保存先。計測条件はすべてここで管理する |
| [src/slr/](src/slr/) | import して使う部品。`config.py`（設定とパス解決）、`camera.py`（カメラ制御）、`projector.py`（全画面投影）、`patterns.py`（パターン生成）、`capture.py`（投影と撮影の共通処理）、`decode.py`（プロジェクタ座標の復元）、`calibration.py`（カメラ・プロジェクタの校正）、`reconstruct.py`（三角測量と点群出力）、`evaluate.py`（既知形状との比較による精度評価）、`render.py`（点群の描画）、`cli.py`（エラー表示） |
| [scripts/](scripts/) | 直接実行するスクリプト。番号順に実行する |
| [tests/](tests/) | 実機なしで確認できる範囲の自動テスト |
| `data/` | 投影パターン、撮影画像、処理結果。Git 管理外 |
| `reference/` | 移植元として参照しているコード。Git 管理外 |
| `pyproject.toml` / `uv.lock` / `.python-version` | プロジェクトと Python 環境の管理 |

`setup/` は機器を使えるようにするための準備で、すでに役目を終えています。現在の作業は `src/` と `scripts/` で行います。

構成の方針は次のとおりです。`src/` にあるものは必ず import される部品、`scripts/` にあるものは必ず直接実行するもので、この境界を保ちます。解像度や露光のような値は `config/default.toml` の 1 箇所だけに書き、複数箇所に散らして食い違うのを防ぎます。投影パターンは `data/patterns/1920x1080/` のように解像度をディレクトリ名に含め、別解像度のパターンを取り違えて投影できないようにしています。パスは `pyproject.toml` の位置を起点に解決するため、どのディレクトリから実行しても同じ場所を指します。

## 実行方法

初回の環境構築は [setup/setup.md](setup/setup.md) を参照してください。以下は環境構築後に、プロジェクトのルートディレクトリで実行するコマンドです。

Python でカメラを使う前に、SpinView を終了してください。カメラは同時に 1 つのアプリケーションからしか開けません。

各コマンドの下に、2026-09-25 に実際に実行したときのコマンドと結果を載せています。実験名は計測が `test04`、キャリブレーションが `calib01` です。

### 0. 機材の動作確認

```powershell
uv run --no-sync python scripts/00_check_hardware.py
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/00_check_hardware.py
設定: C:\Users\souya\Projects\structured-light-reconstruction\config\default.toml

--- カメラ ---
カメラ: Blackfly S BFS-U3-23S3C (S/N 23594307)
カメラ設定:
  バッファ    : NewestOnly
  画素形式    : BayerRG16
  ガンマ      : 1.0
  ゲイン      : 0.00 dB
  フレームレート: 19.61 fps
  露光時間    : 50003 us
  WB (R/B)    : 1.528 / 2.433
  撮影テスト  : 1920 x 1200 uint16
  輝度        : 最小 774 / 平均 31628.1 / 最大 65530
  OK

--- プロジェクタ ---
  表示位置    : (1920, 0)
  投影解像度  : 1920 x 1080
  表示中      : white
  表示中      : black
  表示中      : pattern_00
  表示中      : pattern_20
  OK
```

`--camera-only` / `--projector-only` で片方だけ確認できます。

</details>

### 1. 投影パターンの生成

初回のみ必要です。解像度を変えたときは `--force` で再生成します。

```powershell
uv run --no-sync python scripts/01_generate_patterns.py
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/01_generate_patterns.py
設定       : C:\Users\souya\Projects\structured-light-reconstruction\config\default.toml
投影解像度 : 1920 x 1080
生成枚数   : 46 枚（グレイコード 44 枚 + マスク用 2 枚）
保存先     : C:\Users\souya\Projects\structured-light-reconstruction\data\patterns\1920x1080
manifest   : manifest.json
```

既にパターンがあると上書きせずに止まります。

```
> uv run --no-sync python scripts/01_generate_patterns.py
すでにパターンがあります: ...\data\patterns\1920x1080
上書きするには --force を付けてください。
```

</details>

### 2. キャリブレーション

**計測より先に行います。** 校正と計測のあいだでカメラ・プロジェクタが動くと校正結果が無効になるため、校正してから対象物だけを入れ替えるのが安全です。

1 姿勢につき 2 段階で撮影します。**交点検出用の 1 枚は部屋の照明を点けて撮り**、グレイコードは照明を消して撮ります。光沢のあるボードにプロジェクタの光を当てると、微細な鏡面反射で白マスと黒マスの区別がつかなくなるためです。スクリプトが照明の ON/OFF を指示し、露光も自動で切り替えます。

```powershell
uv run --no-sync python scripts/04_capture_calibration.py <実験名> --poses 12
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/04_capture_calibration.py calib01 --poses 12

--- 姿勢 1 / 12 ---
  [1] ボードを置き、部屋の照明を点けて Enter（やめるなら q）:
    [1/4] 露光  19999 us / 上位0.5%点  6444 / 飽和  0.0%  -> 交点 40 点
  [2] 部屋の照明を消して Enter:
    撮影完了（55 秒）
```

交点が検出できないときは露光を変えて自動で撮り直します。それでも駄目なら画像を `data/raw/<実験名>/failed/` に保存し、どの交点数なら検出できたかを表示します。

12 姿勢で 15 分ほどかかります。途中で `q` を入力すれば中断でき、同じ実験名で再実行すると続きから再開します。

</details>

```powershell
uv run --no-sync python scripts/05_calibrate.py <実験名>
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/05_calibrate.py calib01
設定       : C:\Users\souya\Projects\structured-light-reconstruction\config\default.toml
ボード     : 交点 8 x 5、1 マス 10.0 mm
姿勢       : 12 件

  pose_02: 交点 40 点（部屋の照明） / 有効画素 52%
  pose_03: 交点 40 点（部屋の照明） / 有効画素 38%
  （中略）
  pose_18: 交点 40 点（部屋の照明） / 有効画素 35%

使用する姿勢: 12 / 12 件

再投影誤差（画素、小さいほど良い。1.0 未満が目安）:
  カメラ      : 0.2031
  プロジェクタ: 0.2351
  ステレオ    : 0.4643

カメラ焦点距離      : fx=4681.4 fy=4670.5
プロジェクタ焦点距離: fx=2464.4 fy=2482.8
基線長（カメラ-プロジェクタ間）: 688.0 mm

保存先: ...\data\results\calib01\calibration.json
```

**再投影誤差が 1.0 画素未満であれば十分です。** 大きい場合は、ボードのたわみ、姿勢のばらつき不足、1 マスの実寸の設定ずれを疑います。

ボードの交点数が分からない場合は `--probe` で実測できます。OpenCV が扱うのはマスの数ではなく内側の交点の数で、マスが 9 × 6 なら交点は 8 × 5 です。

```
> uv run --no-sync python scripts/05_calibrate.py calib01 --probe
```

</details>

### 3. 計測対象の撮影

```powershell
uv run --no-sync python scripts/02_capture.py <実験名>
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/02_capture.py test04
```

石膏像を撮影しました。46 枚を 57.5 秒で保存しています（露光 5000 µs、待機 1.0 秒）。保存先は `data/raw/test04/` で、撮影条件は同じ場所の `metadata.json` に残ります。

既存の実験名を指定するとエラーで止まります。条件の違う画像が混ざるのを防ぐためです。

</details>

### 4. デコード

```powershell
uv run --no-sync python scripts/03_decode.py <実験名>
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/03_decode.py test04 --force --bits
設定       : C:\Users\souya\Projects\structured-light-reconstruction\config\default.toml
入力       : ...\data\raw\test04
使わないビット: 2（最も細かい側から）

ビットごとの通過率（影マスク内）:
  縞幅(投影画素)  通過率
        1024    97.6%  #######################################
         512   100.0%  #######################################
         256    99.4%  #######################################
         128    95.0%  #####################################
          64    97.6%  #######################################
          32    89.0%  ###################################
          16    86.9%  ##################################
           8    83.9%  #################################
           4    77.6%  ###############################
           2    51.0%  ####################
           1    10.3%  ####
  （縦方向も同様に 11 行）

カメラ解像度: 1920 x 1200
有効画素   : 921,851 / 2,304,000（40.0%）
保存先     : ...\data\results\test04
```

`--bits` は診断用です。**縞幅の細かいパターンはレンズのぼけで潰れるため、通過率が急に落ちます。** 落ちる本数を `config/default.toml` の `skip_fine_bits` に設定すると、そのビットを使わずにデコードします。分解能は粗くなりますが有効画素は大きく増えます。

| `skip_fine_bits` | 分解能 | 有効画素率（実測） |
| --- | --- | --- |
| 0 | 1 投影画素 | 0.2% |
| 1 | 2 投影画素 | 9.7% |
| 2 | 4 投影画素 | 40.0% |
| 3 | 8 投影画素 | 58.7% |

`preview_x.png` / `preview_y.png` が滑らかなグラデーションになっていれば正しく復号できています。

</details>

### 5. 三次元復元

```powershell
uv run --no-sync python scripts/06_reconstruct.py <実験名> --calibration <校正の実験名>
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/06_reconstruct.py test04 --calibration calib01
設定       : C:\Users\souya\Projects\structured-light-reconstruction\config\default.toml
校正       : ...\data\results\calib01\calibration.json
  再投影誤差: カメラ 0.203 / プロジェクタ 0.235 画素
  基線長    : 688 mm
入力       : ...\data\raw\test04
有効画素   : 921,851 / 2,304,000（40.0%）

三次元点   : 435,491 点（有効画素の 47.2%）
奥行き     : 586 - 745 mm
再投影誤差 : 中央値 0.485 画素

保存先: ...\data\results\test04\points.ply
        ...\data\results\test04\depth.png
```

</details>

### 6. 形状の確認

```powershell
uv run --no-sync python scripts/08_render.py <実験名>
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python scripts/08_render.py test04
入力   : ...\data\results\test04\points.npy
点数   : 435,491
着色   : 撮影画像の色
静止画 : ...\data\results\test04\views（6 枚）
GIF    : ...\data\results\test04\turntable.gif（36 コマ、1.9 MB）
```

`turntable.gif` を開くと、視点を左右に振ったアニメーションで形を確認できます。**静止画では奥行きが分かりにくいので、まず GIF を見てください。** `--color depth` を付けると奥行きによる着色（手前が青、奥が赤）になり、表面の起伏が見やすくなります。

点群ビューア（[CloudCompare](https://www.cloudcompare.org/) など）を入れていれば `points.ply` を直接開けますが、入れていなくてもこの GIF で確認できます。

</details>

### 7. 精度評価

```powershell
uv run --no-sync python scripts/07_evaluate.py <実験名> --shape plane
```

<details>
<summary>実行例</summary>

背景の壁（画面左側）を平面として評価した例です。

```
> uv run --no-sync python scripts/07_evaluate.py test04 --shape plane --roi 0,0,550,1200 --note "背景の壁、距離約700mm"
入力       : ...\data\results\test04\points.npy
点数       : 435,491
範囲       : x=0 y=0 幅=550 高さ=1200 -> 156,059 点

当てはめ   : plane
  normal        : [-0.437, 0.046, -0.898]
  distance_mm   : 597.659
  tilt_deg      : 26.05

形状からのずれ（内点のみ）:
  RMS         : 0.380 mm
  平均絶対誤差: 0.320 mm
  最大         : 1.935 mm
  内点の割合   : 100.0%（156,059 / 156,059 点）

保存先: ...\data\results\test04\evaluation_plane.json
        ...\data\results\test04\residual_plane.png
```

**RMS が計測精度の指標です。** 距離約 600 mm で 0.380 mm、相対 0.06% でした。

`--roi` は `x,y,幅,高さ` の順で、カメラ画像の画素座標です。`depth.png` を見ながら決めてください。省略すると点群全体を使います。

球を使うとスケールの系統誤差が見えます（平面では検出できません）。

```powershell
uv run --no-sync python scripts/07_evaluate.py <実験名> --shape sphere --diameter 50.0
```

</details>

プロジェクタは Windows の拡張表示で、メイン画面の右隣・上端揃えに配置します。別の配置にする場合は `config/default.toml` の `[projector]` で `auto = false` にして座標を指定します。撮影中は `Esc` で中断できます。

### テスト

実機を使わずに確認できる範囲の自動テストです。

```powershell
uv run --no-sync python tests/test_decode_roundtrip.py
uv run --no-sync python tests/test_calibration.py
uv run --no-sync python tests/test_reconstruct.py
uv run --no-sync python tests/test_evaluate.py
uv run --no-sync python tests/test_render.py
```

<details>
<summary>実行例</summary>

```
> uv run --no-sync python tests/test_decode_roundtrip.py
往復テスト:
  64 x 48: OK（6+6 bit, 24 枚, 全画素一致）
  100 x 80: OK（7+7 bit, 28 枚, 全画素一致）
  1920 x 1080: OK（11+11 bit, 44 枚, 全画素一致）

ビットを飛ばした場合:
  64 x 48 skip=1: OK（2 投影画素単位, 有効 100.0%）
  64 x 48 skip=2: OK（4 投影画素単位, 有効 100.0%）
  1920 x 1080 skip=2: OK（4 投影画素単位, 有効 100.0%）

異常系:
  枚数不足を検出: OK（パターン画像が 22 枚ですが、64x48 には 24 枚必要です）

すべて成功しました。
```

```
> uv run --no-sync python tests/test_reconstruct.py
平面の復元:
  歪みなし 深さ 1000 mm 傾き +0.00: OK（3,420 点、誤差 中央値 0.231 mm / 最大 0.584 mm）
  歪みあり 深さ 1000 mm 傾き +0.10: OK（3,420 点、誤差 中央値 0.233 mm / 最大 0.605 mm）

異常値の除外:
  奥行き範囲外を除外: OK
  誤った対応を除外: OK（残ったのは 50%）

書き出し:
  PLY の書き出し: OK（3,420 点）

すべて成功しました。
```

```
> uv run --no-sync python tests/test_evaluate.py
平面の当てはめ:
  ノイズ  0.10 mm -> RMS 0.0991 mm（傾き 19.8°, 距離 700.0 mm）
  ノイズ  1.00 mm -> RMS 0.9914 mm（傾き 19.8°, 距離 700.0 mm）
  別物体 900 点を混入 -> 距離 700.00 mm、内点 82%、RMS 0.297 mm

球の当てはめ:
  半径  25.0 mm / ノイズ 0.20 mm -> 推定半径 24.999 mm（誤差 -0.001 mm）、中心のずれ 0.016 mm

すべて成功しました。
```

これらのテストは実機を使いません。撮影データもキャリブレーション結果も不要で、いつでも実行できます。

</details>

### PySpin の扱い

PySpin は PyPI で配布されておらず、配布 wheel を `uv pip install` で導入するため `pyproject.toml` / `uv.lock` の管理外です。そのため、スクリプトの実行には `uv run --no-sync` を使います。

依存を同期するときも `--inexact` を付けます。素の `uv sync` は管理外のパッケージを削除するため、PySpin が消えます。

```powershell
uv sync --inexact
```

PySpin が利用できなくなった場合は、wheel を再インストールします。毎回の実行前にインストールする必要はありません。

```powershell
uv pip install ".\setup\vendor\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl"
```

## 今後の進め方

実際に機材を動かしながら、各段階の手順・設定・結果を [docs/measurement.md](docs/measurement.md) に記録します。

1. **暗室への設置**  
   カメラ・プロジェクタ・対象物の配置を決め、固定します。投影範囲とカメラの撮影範囲が重なるように調整します。
2. **撮影条件の調整と自動撮影の確認**  
   ピント・絞り・露光・ゲインなどを調整し、白・黒・縞で写りを確認します。その配置で自動投影・撮影を試し、パターンと保存画像の対応、切り替え後の待機時間、保存内容を確認します。
3. **キャリブレーション**  
   校正用ターゲットと手法を決め、必要な画像を撮影します。カメラとプロジェクタの内部パラメータ・歪み、および両者の相対位置・姿勢を求め、校正結果を確認します。方式に応じて、この段階でグレーコードの生成・撮影・デコードも準備します。
4. **計測対象の撮影**  
   校正時の機器配置と光学条件を維持し、対象物にパターンを投影して撮影します。画像と撮影設定、使用した校正結果を対応付けて保存します。
5. **三次元復元と評価**  
   パターンをデコードして対応点を求め、信頼できる画素を選別して三角測量を行います。点群を出力し、既知形状などで結果を評価します。

自動撮影はまずパターン表示後に待機して撮影する方式で検証します。ハードウェア同期の成立や、三次元計測の精度が確認できている段階ではありません。

## 記録・管理の方針

- README には、プロジェクトの目的・構成・進捗・手順書への入口をまとめます。
- セットアップの再現手順は `setup/setup.md`、暗室での計測手順は `docs/measurement.md`、撮影後の処理手順は `docs/reconstruction.md` にまとめます。
- 撮影ごとの画像・設定・校正結果を区別して保存し、後から条件を追えるようにします。
- ソースコードと手順書は Git で管理し、仮想環境・配布インストーラ・大量の撮影データは Git 管理対象から除外する方針です。撮影データと校正結果は別途バックアップします。
