"""プロジェクタへのパターン全画面表示。

Tkinter と Pillow を使い、拡張ディスプレイ側に座標を指定して枠なしウィンドウを
出します。pygame の FULLSCREEN のようにメインディスプレイを占有しないので、
プロジェクタを 2 画面目のまま使えて PC 側の画面も潰れません。

``mainloop()` は使わず、``show()`` のたびに ``update()`` でイベントを処理して
描画を確定させます。撮影ループ側から同期的に駆動するためです。
"""

from __future__ import annotations

import ctypes
import tkinter as tk
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk

from .config import Config


def _enable_dpi_awareness() -> None:
    """Windows の拡大率による座標・サイズのずれを防ぐ。

    プロセスごとに一度しか設定できず、二度目は失敗するため例外は握りつぶします。
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


def _primary_screen_width() -> int:
    """メインディスプレイの幅（物理ピクセル）。"""
    return ctypes.windll.user32.GetSystemMetrics(0)


class Projector:
    """パターンを全画面表示するウィンドウ。

    with 文で使います。

        with Projector(config) as projector:
            projector.show(image)
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._item: int | None = None
        # PhotoImage は参照を持っておかないとガベージコレクトされ、
        # 画面が真っ白になります。
        self._photo: ImageTk.PhotoImage | None = None
        self.aborted = False

    @property
    def position(self) -> tuple[int, int]:
        """表示位置。auto ならメイン画面の右隣・上端揃え。"""
        projector = self._config.projector
        if projector.auto:
            return _primary_screen_width(), 0
        return projector.x, projector.y

    def open(self) -> Projector:
        _enable_dpi_awareness()

        width, height = self._config.projector.size
        x, y = self.position

        root = tk.Tk()
        root.title("Structured light projector")
        root.overrideredirect(True)  # タイトルバー・枠を消す
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.attributes("-topmost", True)
        root.configure(background="black")

        canvas = tk.Canvas(
            root,
            width=width,
            height=height,
            background="black",
            highlightthickness=0,
            borderwidth=0,
            cursor="none",
        )
        canvas.pack(fill="both", expand=True)

        # Esc で撮影を中断できるようにする。実際の中断判定は撮影ループ側で
        # aborted を見て行います。
        root.bind("<Escape>", self._on_escape)
        root.after(200, root.focus_force)

        self._root = root
        self._canvas = canvas
        self._refresh()
        return self

    def _on_escape(self, event: object = None) -> None:
        self.aborted = True

    def show(self, image: np.ndarray | Image.Image | Path | str) -> None:
        """1 枚のパターンを表示し、描画が終わるまで待つ。"""
        if self._root is None or self._canvas is None:
            raise RuntimeError("Projector が open されていません")

        picture = self._to_pil(image)
        if picture.size != self._config.projector.size:
            raise ValueError(
                f"パターンのサイズ {picture.size[0]}x{picture.size[1]} が投影解像度 "
                f"{self._config.projector.width}x{self._config.projector.height} と一致しません"
            )

        self._photo = ImageTk.PhotoImage(picture)
        if self._item is None:
            self._item = self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self._canvas.itemconfigure(self._item, image=self._photo)
        self._refresh()

    def _refresh(self) -> None:
        assert self._root is not None
        self._root.update_idletasks()
        self._root.update()

    @staticmethod
    def _to_pil(image: np.ndarray | Image.Image | Path | str) -> Image.Image:
        if isinstance(image, Image.Image):
            return image
        if isinstance(image, np.ndarray):
            return Image.fromarray(image)
        return Image.open(image)

    def close(self) -> None:
        if self._root is not None:
            self._root.destroy()
            self._root = None
            self._canvas = None
            self._item = None
            self._photo = None

    def __enter__(self) -> Projector:
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
