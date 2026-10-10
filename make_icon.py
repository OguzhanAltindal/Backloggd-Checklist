"""Generate icon.ico (a white check mark on a pink rounded square) with the standard library only."""

import struct
import zlib
from pathlib import Path

BG = (229, 71, 107)
FG = (255, 255, 255)


def dist_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def coverage(d, edge):
    """Anti-aliased coverage for a shape whose boundary is at distance `edge`."""
    return max(0.0, min(1.0, edge - d + 0.5))


def render(size):
    s = size / 256
    radius, stroke = 56 * s, 13 * s
    check = [(70 * s, 132 * s), (112 * s, 174 * s), (190 * s, 88 * s)]
    rows = []
    for y in range(size):
        row = bytearray([0])  # PNG filter type: none
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            # rounded square
            qx = max(radius - px, 0, px - (size - radius))
            qy = max(radius - py, 0, py - (size - radius))
            a_bg = coverage((qx * qx + qy * qy) ** 0.5, radius) if qx and qy else 1.0
            if px < 0 or py < 0:
                a_bg = 0
            d = min(dist_to_segment(px, py, *check[0], *check[1]),
                    dist_to_segment(px, py, *check[1], *check[2]))
            a_fg = coverage(d, stroke)
            r, g, b = (round(BG[i] * (1 - a_fg) + FG[i] * a_fg) for i in range(3))
            row += bytes((r, g, b, round(255 * a_bg)))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(n) for n in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for n, png in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    out = Path(__file__).parent / "icon.ico"
    out.write_bytes(header + entries + b"".join(images))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
