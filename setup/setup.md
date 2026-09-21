# Windowsでのカメラ・プロジェクタのセットアップ

## 1. この手順の完了条件

次の動作ができれば、基本セットアップは完了です。

- SpinViewでFLIRカメラの映像を表示し、静止画を保存できる。
- Pythonからカメラを認識して、PNGを1枚保存できる。
- Pythonからプロジェクタに白・黒・縞を全画面表示できる。

露光・ピントの調整、グレーコード生成、自動撮影、キャリブレーションは `measurement.md` で扱います。

## 2. 使用環境

| 項目 | 動作確認した構成 |
| --- | --- |
| OS | Windows 64bit |
| カメラ | FLIR Blackfly S BFS-U3-23S3C |
| 接続 | カメラ付属のUSB 3ケーブル |
| プロジェクタ | BenQ・HDMI接続 |
| 投影設定 | 800 × 600、60 Hz、拡大率100% |
| Spinnaker SDK / SpinView | 4.4.0.246（x64） |
| PySpin | spinnaker_python 4.4.0.246、cp312、win_amd64 |
| uv | 0.12.13 |
| Python | CPython 3.12.14 |
| エディタ | Visual Studio Code |

プロジェクタの800 × 600は、使用機のWindows推奨設定です。本体の型番・ネイティブ解像度は未確認です。別の機材では仕様を確認して設定してください。

## 3. フォルダ構成

`setup` はプロジェクト直下に置きます。環境管理ファイルはプロジェクト直下に残します。

| 配置先 | 内容 |
| --- | --- |
| `setup/setup.md` | この手順書 |
| `setup/check_camera.py` | カメラ認識確認 |
| `setup/capture_one.py` | 1枚撮影・保存確認 |
| `setup/projector_test.py` | 白・黒・縞の表示確認 |
| `setup/installers/` | SDKのEXEとPySpinのZIP |
| `setup/vendor/spinnaker_python-4.4.0.246-cp312-cp312-win_amd64/` | PySpin ZIPの展開内容一式 |
| `setup/captures/` | 撮影テスト画像（スクリプトが作成） |
| `.venv/` | プロジェクト共通の仮想環境 |
| `pyproject.toml`、`uv.lock`、`.python-version` | uvの管理ファイル |
| `.gitignore` | Gitの除外設定 |

Spinnaker SDKのインストール先はインストーラの既定値を使います。インストール済みの `C:\Program Files\Teledyne\Spinnaker` は移動しません。

以下のコマンドは、特記がなければWindows PowerShellで実行します。

## 4. uvとプロジェクトの準備

[uv公式サイト](https://docs.astral.sh/uv/)のWindows用インストーラでuvを導入します。

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

PowerShellを開き直して確認します。

```powershell
uv --version
```

新規プロジェクトを作成します。`$env:USERPROFILE` は自分のユーザーフォルダを表します。

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Projects"
Set-Location "$env:USERPROFILE\Projects"
uv init --python 3.12 structured-light-reconstruction
Set-Location structured-light-reconstruction
uv sync
uv run python --version
New-Item -ItemType Directory -Force setup, setup\installers, setup\vendor
```

Python 3.12.xと表示されれば成功です。既存プロジェクトを使う場合は、そのフォルダへ移動して `uv sync` を実行し、新規作成部分は省略します。

## 5. SDKとPySpinの取得

[TeledyneのSpinnaker SDKページ](https://www.flir.com/products/spinnaker-sdk/)から、次のWindows 64bit用ファイルを取得します。必要に応じてアカウントにログインします。

- `SpinnakerSDK_FULL_4.4.0.246_x64.exe`
- `spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.zip`

両方を `setup/installers/` に保管します。

PySpinのZIPを「すべて展開」で、以下へ展開します。

```text
setup/vendor/spinnaker_python-4.4.0.246-cp312-cp312-win_amd64/
```

このフォルダの直下に、`docs`、`Examples`、`licenses`、`README.md`、次のwheelがあることを確認します。

```text
spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl
```

SDKとPySpinのバージョン、およびPython 3.12・Windows 64bitの組み合わせを揃えます。

## 6. Spinnaker SDKのインストール

カメラをPCから外して、取得したEXEを起動します。

1. ライセンスを確認して進みます。
2. 任意のAnalytics Data Collectionは、チェックを入れずに進めます。
3. Installation Profileで **Application Development** を選択します。
4. Installation Componentsは既定選択を維持します。USB Driver、USB Driver Legacy、Runtime Files、Utilities、SpinViewが含まれていることを確認します。
5. GigE Interfaces画面では、USB接続のみ使用するためインターフェースを選択しません。
6. インストール完了後、Windowsを再起動します。

## 7. SpinViewで撮影確認

1. カメラを専用ケーブルでPCのUSB 3端子へ直接接続します。
2. スタートメニューからSpinViewを起動します。
3. Devices一覧でカメラを選択します。
4. 緑色の再生ボタンでライブ表示を開始します。
5. Save Image機能でPNGを保存し、画像を開いて確認します。
6. Pythonから操作する前にSpinViewを終了します。

## 8. PySpinとTkinterの確認

プロジェクト直下で実行します。

```powershell
uv pip install ".\setup\vendor\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl"
uv run --no-sync python -c "import PySpin; print('PySpin import OK')"
uv run --no-sync python -c "import tkinter; print('Tkinter OK')"
```

それぞれ `PySpin import OK`、`Tkinter OK` と表示されれば成功です。

この手順ではPySpinを `uv pip install` で直接導入します。PySpinは `pyproject.toml` / `uv.lock` には登録されません。`uv sync` で削除された場合や仮想環境を再作成した場合は、上記のwheelインストールを再実行してください。テストは `uv run --no-sync` で実行します。

## 9. Pythonからカメラを確認する

以下を `setup/check_camera.py` に保存します。

```python
import PySpin

system = PySpin.System.GetInstance()
cameras = None
try:
    cameras = system.GetCameras()
    print(f"Camera count: {cameras.GetSize()}")
    for index in range(cameras.GetSize()):
        camera = cameras.GetByIndex(index)
        try:
            info = camera.GetTLDeviceNodeMap()
            model = PySpin.CStringPtr(info.GetNode("DeviceModelName"))
            serial = PySpin.CStringPtr(info.GetNode("DeviceSerialNumber"))
            print(f"Model: {model.GetValue()}")
            print(f"Serial: {serial.GetValue()}")
        finally:
            del camera
finally:
    if cameras is not None:
        cameras.Clear()
    system.ReleaseInstance()
```

SpinViewを閉じ、カメラを接続して実行します。

```powershell
uv run --no-sync python setup/check_camera.py
```

`Camera count: 1` と、使用カメラの型番・シリアル番号が表示されれば成功です。

## 10. Pythonから1枚撮影する

以下を `setup/capture_one.py` に保存します。

```python
from datetime import datetime
from pathlib import Path
import PySpin


def main():
    output_dir = Path(__file__).resolve().parent / "captures"
    output_dir.mkdir(exist_ok=True)
    system = PySpin.System.GetInstance()
    cameras = None
    camera = None
    image = None
    initialized = False
    acquiring = False

    try:
        cameras = system.GetCameras()
        if cameras.GetSize() != 1:
            raise RuntimeError(
                f"Expected 1 camera, found {cameras.GetSize()}"
            )
        camera = cameras.GetByIndex(0)
        camera.Init()
        initialized = True
        camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)
        camera.AcquisitionMode.SetValue(
            PySpin.AcquisitionMode_Continuous
        )
        camera.BeginAcquisition()
        acquiring = True
        image = camera.GetNextImage(5000)

        if image.IsIncomplete():
            raise RuntimeError(
                f"Incomplete image: status={image.GetImageStatus()}"
            )

        processor = PySpin.ImageProcessor()
        processor.SetColorProcessing(
            PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR
        )
        converted = processor.Convert(image, PySpin.PixelFormat_RGB8)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_path = output_dir / f"capture_{timestamp}.png"
        converted.Save(str(output_path))
        print(f"Saved: {output_path}")
        print(f"Size: {image.GetWidth()} x {image.GetHeight()}")
    finally:
        if image is not None:
            image.Release()
        try:
            if acquiring:
                camera.EndAcquisition()
        finally:
            try:
                if initialized:
                    camera.DeInit()
            finally:
                camera = None
                if cameras is not None:
                    cameras.Clear()
                system.ReleaseInstance()


if __name__ == "__main__":
    main()
```

実行します。

```powershell
uv run --no-sync python setup/capture_one.py
```

`setup/captures/` に日時付きPNGが保存され、画像を開ければ成功です。露光・ゲインは現在のカメラ設定を使います。RGB8への変換は表示確認用であり、計測用の画素形式・明るさは別途設定します。

## 11. プロジェクタの接続・表示設定

1. PCとプロジェクタをHDMIで接続して電源を入れます。
2. `Win + P` で「拡張」を選択します。
3. Windowsの「ディスプレイ設定」で「識別」を押し、PCを画面1、プロジェクタを画面2として確認します。
4. PCをメインディスプレイにし、配置図で画面2を画面1の右隣へ、上端を揃えて配置します。
5. プロジェクタ側を800 × 600、60 Hz、拡大率100%、横向きに設定します。
6. ディスプレイの詳細設定でデスクトップモード・アクティブなシグナルモードの両方が800 × 600であることを確認します。
7. プロジェクタ本体の設定で台形補正を0、自動台形補正があればOFFにします。

次のテストコードは、この2画面配置と解像度を前提とします。

## 12. Pythonから全画面表示する

以下を `setup/projector_test.py` に保存します。

```python
import ctypes
import tkinter as tk

ctypes.windll.shcore.SetProcessDpiAwareness(2)

WIDTH = 800
HEIGHT = 600
STRIPE_WIDTH = 40
projector_x = ctypes.windll.user32.GetSystemMetrics(0)

root = tk.Tk()
root.title("Projector test")
root.overrideredirect(True)
root.geometry(f"{WIDTH}x{HEIGHT}+{projector_x}+0")
root.attributes("-topmost", True)

canvas = tk.Canvas(
    root, width=WIDTH, height=HEIGHT,
    background="black", highlightthickness=0, cursor="none",
)
canvas.pack(fill="both", expand=True)


def show_stripes(event=None):
    canvas.delete("all")
    canvas.configure(background="black")
    for x in range(0, WIDTH, STRIPE_WIDTH * 2):
        canvas.create_rectangle(
            x, 0, x + STRIPE_WIDTH, HEIGHT,
            fill="white", outline=""
        )


def show_solid(color):
    canvas.delete("all")
    canvas.configure(background=color)


root.bind("<Escape>", lambda event: root.destroy())
root.bind("<KeyPress-w>", lambda event: show_solid("white"))
root.bind("<KeyPress-b>", lambda event: show_solid("black"))
root.bind("<KeyPress-s>", show_stripes)

show_stripes()
root.after(200, root.focus_force)
root.mainloop()
```

実行します。

```powershell
uv run --no-sync python setup/projector_test.py
```

| キー（英数入力・小文字） | 動作 |
| --- | --- |
| W | 全白 |
| B | 全黒 |
| S | 白黒の縦縞 |
| Esc | 終了 |

プロジェクタの表示領域いっぱいに模様が出て、タイトルバー・タスクバーが見えず、キーで切り替えられれば成功です。キーが効かない場合は表示ウィンドウをクリックしてフォーカスを移します。

## 13. Gitとファイルの保管

Gitには手順書、確認用Pythonスクリプト、プロジェクト直下のuv管理ファイルを保存します。

プロジェクト直下の `.gitignore` に以下を追加します。既存の内容は残してください。

```gitignore
.venv/
__pycache__/
setup/installers/
setup/vendor/
setup/captures/
```

インストーラとvendorフォルダは手元で保管します。Gitから複製した別PCでは手順5に従って配布物を取得します。`setup` 全体をGitから除外しないでください。

## 14. 環境を再作成するとき

Windows版Spinnaker SDKをインストールし、配布物を指定位置へ配置したうえで、プロジェクト直下で実行します。

```powershell
uv sync
uv pip install ".\setup\vendor\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl"
uv run --no-sync python setup/check_camera.py
uv run --no-sync python setup/capture_one.py
uv run --no-sync python setup/projector_test.py
```

## 完了チェック

- [ ] SpinViewでライブ表示・静止画保存ができた。
- [ ] PySpinとTkinterをimportできた。
- [ ] Pythonからカメラの型番・シリアル番号を取得できた。
- [ ] PythonからPNGを保存できた。
- [ ] プロジェクタへ白・黒・縞を全画面表示できた。

すべて確認したら `measurement.md` の撮影準備へ進みます。

