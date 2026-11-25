"""Regenerates assets/icon.ico (a download-arrow badge) using only PySide6.

Run from the repo root:  python packaging/make_icon.py

The .ico embeds one PNG per size, which Windows Vista+ supports natively,
so no Pillow dependency is needed.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPolygonF

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"


def render(size: int) -> bytes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0

    badge = QPainterPath()
    badge.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)
    p.fillPath(badge, QColor("#d32f2f"))

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    p.drawRect(QRectF(104 * s, 48 * s, 48 * s, 84 * s))
    p.drawPolygon(QPolygonF([QPointF(60 * s, 124 * s), QPointF(196 * s, 124 * s), QPointF(128 * s, 192 * s)]))

    pen = QPen(QColor("white"), max(1.0, 18 * s), Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(64 * s, 214 * s), QPointF(192 * s, 214 * s))
    p.end()

    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(data)


def main() -> int:
    _app = QGuiApplication(sys.argv)
    pngs = [render(size) for size in SIZES]

    header = struct.pack("<HHH", 0, 1, len(SIZES))
    offset = len(header) + 16 * len(SIZES)
    entries, blobs = b"", b""
    for size, png in zip(SIZES, pngs):
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(header + entries + blobs)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
