#!/usr/bin/env python3
"""make_icons.py — 產生新聞台的 PWA 圖標（SVG + PNG 192/512/maskable + apple-touch）。

設計：深色圓角底 + 一個藍點 + 三條不等長橫線。
一眼就是「新聞列表 / 今天值得看」，不靠中文字（字做小圖標辨識度會掉）。
"""
import os
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
SS = 4                                    # 超取樣（畫大再縮，邊緣才順）
BG_TOP, BG_BOT = (28, 33, 50), (9, 11, 16)
AC_TOP, AC_BOT = (154, 183, 255), (99, 132, 255)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def vgrad(S, top, bot):
    g = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(g)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=lerp(top, bot, y / (S - 1)))
    return g


def draw(size: int, pad_ratio: float = 0.0) -> Image.Image:
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # 圓角底
    r = int(S * 0.225)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=255)
    img.paste(vgrad(S, BG_TOP, BG_BOT), (0, 0), mask)

    inset = S * pad_ratio
    x0 = inset + S * 0.215
    x1 = S - inset - S * 0.215
    span = x1 - x0

    bar = int(span * 0.155)               # 線的粗細
    gap = int(bar * 1.35)
    total = bar * 3 + gap * 2
    y = (S - total) / 2

    # 第一條：藍點 + 藍色漸層線（＝今天值得看）。總寬對齊第二條的右端
    cy = y + bar / 2
    dot_r = bar * 0.60
    d = ImageDraw.Draw(img)
    d.ellipse([x0, cy - dot_r, x0 + dot_r * 2, cy + dot_r * 2],
              fill=lerp(AC_TOP, AC_BOT, 0.15))
    bx = x0 + dot_r * 2 + bar * 0.70
    bw = (x0 + span * 0.86) - bx
    lay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle([bx, y, bx + bw, y + bar],
                                          radius=bar / 2, fill=(255, 255, 255, 255))
    colored = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    colored.paste(vgrad(S, AC_TOP, AC_BOT), (0, 0), lay.split()[3])
    img.alpha_composite(colored)

    # 第二條：白
    d = ImageDraw.Draw(img)
    y2 = y + bar + gap
    d.rounded_rectangle([x0, y2, x0 + span * 0.86, y2 + bar],
                        radius=bar / 2, fill=(255, 255, 255, 232))
    # 第三條：白（淡，短）
    y3 = y2 + bar + gap
    d.rounded_rectangle([x0, y3, x0 + span * 0.58, y3 + bar],
                        radius=bar / 2, fill=(255, 255, 255, 128))

    return img.resize((size, size), Image.LANCZOS)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.3" y2="1">
      <stop offset="0" stop-color="#1c2132"/>
      <stop offset="1" stop-color="#090b10"/>
    </linearGradient>
    <linearGradient id="ac" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#9ab7ff"/>
      <stop offset="1" stop-color="#6384ff"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="115" fill="url(#bg)"/>
  <circle cx="112" cy="196" r="17" fill="url(#ac)"/>
  <rect x="146" y="185" width="193" height="23" rx="11.5" fill="url(#ac)"/>
  <rect x="90" y="245" width="332" height="24" rx="12" fill="#fff" opacity=".91"/>
  <rect x="90" y="306" width="224" height="24" rx="12" fill="#fff" opacity=".46"/>
</svg>
"""

if __name__ == "__main__":
    with open(os.path.join(OUT, "icon.svg"), "w", encoding="utf-8") as f:
        f.write(SVG)
    for name, size, pad in [
        ("icon-192.png", 192, 0.0),
        ("icon-512.png", 512, 0.0),
        ("icon-maskable-512.png", 512, 0.12),
        ("apple-touch-icon.png", 180, 0.0),
    ]:
        p = os.path.join(OUT, name)
        draw(size, pad).save(p)
        print(f"{name:26} {size}x{size}  {os.path.getsize(p)} bytes")
    print("icon.svg  written")
