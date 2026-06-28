"""Generate gradient app icons with a chat-bubble glyph (stdlib only, no Pillow)."""
import struct
import zlib


def lerp(a, b, t):
    return int(a + (b - a) * t)


def make_png(path: str, size: int) -> None:
    # Diagonal gradient from indigo -> magenta, with a white rounded speech bubble.
    c1 = (108, 123, 255)   # #6c7bff
    c2 = (184, 50, 126)    # #b8327e
    cx, cy = size * 0.5, size * 0.46
    r = size * 0.26
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG filter byte per row
        for x in range(size):
            t = (x + y) / (2 * size)
            rb, gb, bb = lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t)
            # Speech bubble: circle body + small tail toward bottom-left.
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            tail = (x < cx) and (y > cy + r * 0.4) and ((cx - x) + (y - cy) < r * 1.15)
            if d < r or tail:
                rb, gb, bb = 245, 247, 255
            rows += bytes([rb, gb, bb, 255])

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(png)


if __name__ == "__main__":
    make_png("public/icon-192.png", 192)
    make_png("public/icon-512.png", 512)
    print("icons written")
