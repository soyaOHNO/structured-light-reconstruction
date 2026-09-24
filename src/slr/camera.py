"""FLIR カメラ（PySpin）の制御。

構造化光のデコードは「投影した明るさと撮影された明るさが比例する」ことを
前提にしています。そのため自動露光・自動ゲイン・自動ホワイトバランスはすべて
無効にし、ガンマも線形に固定します。設定値は config/default.toml で管理します。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import PySpin

from .config import CameraConfig, Config


@dataclass(frozen=True)
class DeviceInfo:
    model: str
    serial: str


def _clamp(value: float, node: Any, label: str) -> float:
    """ノードの許容範囲に値を丸める。範囲外だった場合は警告を出す。"""
    low, high = node.GetMin(), node.GetMax()
    if not low <= value <= high:
        print(f"  [警告] {label} は {low} 〜 {high} の範囲です。{value} を丸めます。")
    return min(max(value, low), high)


class Camera:
    """撮影用のカメラ 1 台。

    with 文で使います。終了時に取得停止と解放を必ず行います。

        with Camera(config) as camera:
            frames = camera.grab(1)
    """

    def __init__(self, config: Config | CameraConfig) -> None:
        self._config = config.camera if isinstance(config, Config) else config
        self._system: Any = None
        self._camera_list: Any = None
        self._camera: Any = None
        self._acquiring = False
        self._initialized = False
        self.info: DeviceInfo | None = None

    # ------------------------------------------------------------------
    # 接続と解放
    # ------------------------------------------------------------------

    def open(self) -> Camera:
        # PySpin の例外はそのままだと読みにくいので、原因の見当がつく
        # メッセージに変換します。
        try:
            return self._open()
        except PySpin.SpinnakerException as error:
            self.close()
            raise RuntimeError(f"カメラの初期化に失敗しました: {error}") from error

    def _open(self) -> Camera:
        self._system = PySpin.System.GetInstance()
        self._camera_list = self._system.GetCameras()
        count = self._camera_list.GetSize()
        if count != 1:
            self._release()
            raise RuntimeError(
                f"カメラが {count} 台見つかりました（1 台である必要があります）。"
                "SpinView を終了しているか、ケーブルが接続されているか確認してください。"
            )

        self._camera = self._camera_list.GetByIndex(0)
        self._camera.Init()
        self._initialized = True

        nodemap = self._camera.GetTLDeviceNodeMap()
        self.info = DeviceInfo(
            model=PySpin.CStringPtr(nodemap.GetNode("DeviceModelName")).GetValue(),
            serial=PySpin.CStringPtr(nodemap.GetNode("DeviceSerialNumber")).GetValue(),
        )
        print(f"カメラ: {self.info.model} (S/N {self.info.serial})")

        self._apply_settings()
        return self

    def close(self) -> None:
        try:
            if self._acquiring:
                self._camera.EndAcquisition()
                self._acquiring = False
        finally:
            try:
                if self._initialized:
                    self._camera.DeInit()
                    self._initialized = False
            finally:
                self._release()

    def _release(self) -> None:
        # PySpin はカメラへの参照が残っているとシステムを解放できません。
        self._camera = None
        if self._camera_list is not None:
            self._camera_list.Clear()
            self._camera_list = None
        if self._system is not None:
            self._system.ReleaseInstance()
            self._system = None

    def __enter__(self) -> Camera:
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 設定
    # ------------------------------------------------------------------

    def _apply_settings(self) -> None:
        config = self._config
        camera = self._camera
        print("カメラ設定:")

        self._set_buffer_handling(config.buffer_handling)
        self._set_pixel_format(config.pixel_format)

        # トリガは使わず、連続取得したフレームから最新を取り出します。
        camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)
        camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)

        # ガンマ: 1.0 で線形。ガンマ補正が入ると輝度の比例関係が崩れ、
        # グレイコードの大小比較が狂います。
        if camera.GammaEnable.GetAccessMode() == PySpin.RW:
            camera.GammaEnable.SetValue(True)
        if camera.Gamma.GetAccessMode() == PySpin.RW:
            camera.Gamma.SetValue(_clamp(config.gamma, camera.Gamma, "ガンマ"))
        print(f"  ガンマ      : {camera.Gamma.GetValue()}")

        # ゲイン: 自動を切って固定。
        if camera.GainAuto.GetAccessMode() == PySpin.RW:
            camera.GainAuto.SetValue(PySpin.GainAuto_Off)
        if camera.Gain.GetAccessMode() == PySpin.RW:
            camera.Gain.SetValue(_clamp(config.gain_db, camera.Gain, "ゲイン"))
        print(f"  ゲイン      : {camera.Gain.GetValue():.2f} dB")

        # 露光時間より先にフレームレートを決めます。フレームレートが高すぎると
        # 露光時間の上限がそれに縛られるためです。
        self._set_frame_rate(config.exposure_time_us)

        # 露光: 自動を切って固定。
        if camera.ExposureAuto.GetAccessMode() == PySpin.RW:
            camera.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
        if camera.ExposureTime.GetAccessMode() == PySpin.RW:
            camera.ExposureTime.SetValue(
                _clamp(config.exposure_time_us, camera.ExposureTime, "露光時間")
            )
        print(f"  露光時間    : {camera.ExposureTime.GetValue():.0f} us")

        self._set_white_balance(config.white_balance_red, config.white_balance_blue)

    def _set_buffer_handling(self, mode: str) -> None:
        """ストリームバッファの扱いを設定する。

        NewestOnly にしないと、パターンを切り替えた後でもバッファに溜まった
        古いフレームを取得してしまい、投影パターンと撮影画像が 1 枚ずれます。
        この不具合は結果を見ても気づきにくいので、設定できなければ止めます。
        """
        nodemap = self._camera.GetTLStreamNodeMap()
        node = PySpin.CEnumerationPtr(nodemap.GetNode("StreamBufferHandlingMode"))
        if not PySpin.IsReadable(node) or not PySpin.IsWritable(node):
            raise RuntimeError("StreamBufferHandlingMode を設定できません")

        entry = node.GetEntryByName(mode)
        if not PySpin.IsReadable(entry):
            raise RuntimeError(f"バッファモード '{mode}' は使用できません")

        node.SetIntValue(entry.GetValue())
        print(f"  バッファ    : {node.GetCurrentEntry().GetSymbolic()}")

    def _set_pixel_format(self, pixel_format: str) -> None:
        """画素形式を設定する（デコード用に RAW を想定）。"""
        camera = self._camera
        if camera.PixelFormat.GetAccessMode() != PySpin.RW:
            raise RuntimeError("PixelFormat を変更できません")

        entry = camera.PixelFormat.GetEntryByName(pixel_format)
        if not PySpin.IsAvailable(entry):
            raise RuntimeError(
                f"画素形式 '{pixel_format}' はこのカメラで使用できません"
            )
        camera.PixelFormat.SetIntValue(entry.GetValue())
        print(f"  画素形式    : {camera.PixelFormat.ToString()}")

    def _set_frame_rate(self, exposure_time_us: float, announce: bool = True) -> None:
        """露光時間から無理のないフレームレートを決めて設定する。

        露光時間に読み出し分の余裕を足した逆数を上限とし、30 fps で頭打ちに
        します。構造化光の撮影では 1 枚ごとに待機するので高いフレームレートは
        不要です。
        """
        camera = self._camera
        if camera.AcquisitionFrameRateEnable.GetAccessMode() == PySpin.RW:
            camera.AcquisitionFrameRateEnable.SetValue(True)
        if camera.AcquisitionFrameRate.GetAccessMode() != PySpin.RW:
            return

        desired = min(1.0e6 / (exposure_time_us + 1000.0), 30.0)
        camera.AcquisitionFrameRate.SetValue(
            _clamp(desired, camera.AcquisitionFrameRate, "フレームレート")
        )
        if announce:
            print(f"  フレームレート: {camera.AcquisitionFrameRate.GetValue():.2f} fps")

    def _set_white_balance(self, red: float, blue: float) -> None:
        """ホワイトバランスを自動から固定値に切り替える。"""
        camera = self._camera
        if camera.BalanceWhiteAuto.GetAccessMode() != PySpin.RW:
            return
        camera.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Off)

        if camera.BalanceRatioSelector.GetAccessMode() != PySpin.RW:
            return
        for selector, value, label in (
            (PySpin.BalanceRatioSelector_Red, red, "赤"),
            (PySpin.BalanceRatioSelector_Blue, blue, "青"),
        ):
            camera.BalanceRatioSelector.SetValue(selector)
            camera.BalanceRatio.SetValue(
                _clamp(value, camera.BalanceRatio, f"ホワイトバランス({label})")
            )
        print(f"  WB (R/B)    : {red} / {blue}")

    def set_exposure(self, microseconds: float) -> float:
        """露光時間を変更する（取得中でも可）。

        部屋の照明で撮る画像は、プロジェクタで撮る画像よりずっと暗いため、
        姿勢ごとに露光を切り替える必要があります。

        フレームレートが高いままだと露光時間の上限がそれに縛られるので、
        先にフレームレートを下げてから露光を設定します。実際に設定された値を
        返します。
        """
        self._set_frame_rate(microseconds, announce=False)
        camera = self._camera
        if camera.ExposureTime.GetAccessMode() == PySpin.RW:
            camera.ExposureTime.SetValue(
                _clamp(microseconds, camera.ExposureTime, "露光時間")
            )
        return float(camera.ExposureTime.GetValue())

    # ------------------------------------------------------------------
    # 撮影
    # ------------------------------------------------------------------

    def start(self) -> None:
        """取得を開始する。

        パターンごとに開始・停止を繰り返すと 1 枚あたりの待ち時間が増えるため、
        撮影列の最初に一度だけ呼びます。NewestOnly と組み合わせることで、
        待機後に取得したフレームは必ずパターン切り替え後のものになります。
        """
        if not self._acquiring:
            self._camera.BeginAcquisition()
            self._acquiring = True

    def stop(self) -> None:
        if self._acquiring:
            self._camera.EndAcquisition()
            self._acquiring = False

    def grab(self, count: int | None = None, timeout_ms: int = 5000) -> np.ndarray:
        """フレームを取得し、平均した 1 枚を返す。

        ``count`` が 2 以上ならその枚数を平均してノイズを抑えます。返り値の
        dtype は入力と同じ（BayerRG16 なら uint16）です。
        """
        if not self._acquiring:
            raise RuntimeError("start() を呼ぶ前に grab() されました")

        count = count or self._config.frames_per_pattern
        frames = [self._grab_one(timeout_ms) for _ in range(count)]
        if count == 1:
            return frames[0]

        stacked = np.stack(frames).astype(np.float64).mean(axis=0)
        return stacked.round().astype(frames[0].dtype)

    def _grab_one(self, timeout_ms: int) -> np.ndarray:
        try:
            image = self._camera.GetNextImage(timeout_ms)
        except PySpin.SpinnakerException as error:
            raise RuntimeError(
                f"フレームの取得に失敗しました（{timeout_ms} ms でタイムアウト）: {error}"
            ) from error
        try:
            if image.IsIncomplete():
                raise RuntimeError(
                    f"画像が不完全です: status={image.GetImageStatus()}"
                )
            # GetNDArray() は PySpin のバッファを参照しているだけなので、
            # Release() 後に内容が壊れます。必ずコピーを返します。
            return image.GetNDArray().copy()
        finally:
            image.Release()
