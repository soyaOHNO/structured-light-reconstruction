import ctypes
import tkinter as tk

# Windowsの拡大率による座標・サイズのずれを防ぐ。
ctypes.windll.shcore.SetProcessDpiAwareness(2)

WIDTH = 1920
HEIGHT = 1080
STRIPE_WIDTH = 40

# 現在の配置：プロジェクタはメイン画面の右隣・上端揃え。
projector_x = ctypes.windll.user32.GetSystemMetrics(0)

root = tk.Tk()
root.title("Projector test")
root.overrideredirect(True)  # タイトルバー・枠を消す
root.geometry(f"{WIDTH}x{HEIGHT}+{projector_x}+0")
root.attributes("-topmost", True)

canvas = tk.Canvas(
    root,
    width=WIDTH,
    height=HEIGHT,
    background="black",
    highlightthickness=0,
    cursor="none",
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