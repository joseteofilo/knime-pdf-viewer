import struct
import zlib

W = H = 48

RED = (227, 42, 38, 255)
FOLD = (208, 208, 212, 255)
LINE = (130, 130, 135, 255)
CLEAR = (0, 0, 0, 0)


def in_rounded(x, y, x0, y0, x1, y1, r):
    if not (x0 <= x < x1 and y0 <= y < y1):
        return False
    corners = ((x0 + r, y0 + r), (x1 - r - 1, y0 + r), (x0 + r, y1 - r - 1), (x1 - r - 1, y1 - r - 1))
    for cx, cy in corners:
        in_x_corner = x < x0 + r or x >= x1 - r
        in_y_corner = y < y0 + r or y >= y1 - r
        if in_x_corner and in_y_corner and (x - cx) ** 2 + (y - cy) ** 2 > r * r:
            return False
    return True


def pixel(x, y):
    if not in_rounded(x, y, 0, 0, W, H, 9):
        return CLEAR
    px_x0, px_y0, px_x1, px_y1 = 11, 6, 37, 42
    f = 8
    if px_x0 <= x < px_x1 and px_y0 <= y < px_y1:
        in_fold_square = x >= px_x1 - f and y < px_y0 + f
        beyond_hypotenuse = (px_x1 - 1 - x) + (y - px_y0) < f
        if in_fold_square and not beyond_hypotenuse:
            return FOLD
        if not (in_fold_square and beyond_hypotenuse):
            for ly in (16, 17, 23, 24, 30, 31):
                if y == ly and px_x0 + 4 <= x < px_x1 - 5:
                    return LINE
            return (255, 255, 255, 255)
    return RED


def chunk(tag, data):
    raw = tag + data
    return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)


rows = b""
for y in range(H):
    rows += b"\x00" + bytes(v for x in range(W) for v in pixel(x, y))

png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(rows, 9))
    + chunk(b"IEND", b"")
)

with open("src/icons/icon.png", "wb") as fh:
    fh.write(png)

print("wrote src/icons/icon.png", len(png), "bytes")
