"""產生 Meta App 圖示：1024×1024 雷達樣式 PNG（純 stdlib，無需 PIL）

執行：.venv/bin/python scripts/make_icon.py
輸出：deploy/app-icon.png
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

W = H = 1024
BG = (21, 22, 26)        # 深底（同網頁 header）
ACCENT = (59, 110, 246)  # 藍（同網頁 accent）
ACCENT2 = (120, 160, 255)
LIGHT = (240, 240, 245)

CX = CY = 512.0
CORNER_R = 200           # 圓角半徑
RINGS = (190, 300, 410)  # 三圈
RING_W = 9
SWEEP_START, SWEEP_END = -90, -15  # 掃描扇葉角度（度，0=右，逆時針）
SWEEP_R = 410
BLIPS = ((300.0, -60.0, 26), (190.0, 150.0, 22), (410.0, 60.0, 30))  # (半徑, 角度, 尺寸)


def rounded_rect_alpha(x: float, y: float) -> int:
    """圓角方形底 alpha（0 或 255，邊緣 1px 淡出）"""
    m = 24  # 外距
    ax = min(x - m, W - m - x)
    ay = min(y - m, H - m - y)
    d = min(ax, ay)  # 到圓角邊的距離（近似）
    if ax >= CORNER_R or ay >= CORNER_R:
        return 255 if d >= 0 else 0
    # 角落圓角
    kx = max(m + CORNER_R - x, x - (W - m - CORNER_R), 0)
    ky = max(m + CORNER_R - y, y - (H - m - CORNER_R), 0)
    r = math.hypot(kx, ky)
    if r <= CORNER_R - 1:
        return 255
    if r >= CORNER_R + 1:
        return 0
    return int(255 * (CORNER_R + 1 - r) / 2)


def render() -> list[bytes]:
    rows: list[bytes] = []
    for y in range(H):
        row = bytearray()
        for x in range(W):
            r, g, b, a = *BG, 0
            base_alpha = rounded_rect_alpha(x, y)

            dx, dy = x - CX, y - CY
            dist = math.hypot(dx, dy)
            ang = math.degrees(math.atan2(-dy, dx)) % 360  # 0=右，逆時針

            # 掃描扇葉（漸層淡出）
            sa = (ang - SWEEP_START) % 360
            span = (SWEEP_END - SWEEP_START) % 360
            if 0 <= sa <= span and dist <= SWEEP_R:
                fade = 1 - sa / span
                t = 0.18 + 0.5 * fade * fade
                r = int(r * (1 - t) + ACCENT[0] * t)
                g = int(g * (1 - t) + ACCENT[1] * t)
                b = int(b * (1 - t) + ACCENT[2] * t)

            # 三圈雷達
            for ring in RINGS:
                if abs(dist - ring) <= RING_W:
                    t = 0.55
                    r = int(r * (1 - t) + ACCENT2[0] * t)
                    g = int(g * (1 - t) + ACCENT2[1] * t)
                    b = int(b * (1 - t) + ACCENT2[2] * t)

            # 中心點
            if dist <= 26:
                r, g, b = LIGHT

            # 目標光點
            for brad, bang, bsize in BLIPS:
                if abs(dist - brad) <= bsize:
                    bang_diff = abs((ang - bang + 180) % 360 - 180)
                    if bang_diff <= 14:
                        r, g, b = LIGHT

            a = base_alpha
            row += bytes((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), a))
        rows.append(bytes(row))
    return rows


def save_png(path: Path, rows: list[bytes]) -> None:
    raw = b"".join(b"\x00" + row for row in rows)
    idat = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "deploy" / "app-icon.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    save_png(out, render())
    print(f"✅ 圖示已產生：{out}（{out.stat().st_size:,} bytes）")


if __name__ == "__main__":
    main()
