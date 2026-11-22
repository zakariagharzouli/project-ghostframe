"""Transport explicite d'une animation dans une planche de modules visibles."""

import argparse
import io
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

import ghostframe as gf

COLS, ROWS = 56, 32
HEADER = struct.Struct(">4sBBH8sI")
SHARD_BYTES = COLS * ROWS // 8 - HEADER.size
MAX_SHARDS = 8
PITCH, TILE_HEIGHT = 70, 44
MARGIN, DATA_OFFSET = 2, 6
FINDER_LEFT, FINDER_RIGHT, FINDER_BOTTOM = 3, 65, 41


@dataclass(frozen=True)
class Readout:
    motion: gf.Motion
    valid_shards: tuple[int, ...]
    required_shards: int
    repaired_index: int | None


def blocks(payload):
    count = math.ceil(len(payload) / SHARD_BYTES)
    if not 1 <= count <= MAX_SHARDS:
        raise ValueError(f"Capsule limitée à {SHARD_BYTES * MAX_SHARDS} octets utiles")
    padded = payload.ljust(count * SHARD_BYTES, b"\0")
    data = [padded[i:i + SHARD_BYTES] for i in range(0, len(padded), SHARD_BYTES)]
    parity = bytes(SHARD_BYTES)
    for shard in data:
        parity = gf.xor_frame(parity, shard)
    identifier = bytes.fromhex(gf.digest(payload))[:8]
    return [
        HEADER.pack(b"GFC1", index, count, len(payload), identifier, zlib.crc32(shard)) + shard
        for index, shard in enumerate([*data, parity])
    ]


def encode(motion, module=6):
    if not 2 <= module <= 12:
        raise ValueError("Taille de module hors limites")
    parts = blocks(gf.archive_payload(motion, motion.frames[0]))
    width = (len(parts) * PITCH + 2 * MARGIN) * module
    height = (TILE_HEIGHT + 2 * MARGIN) * module
    gf.rgba_length(width, height)
    sheet = Image.new("RGB", (width, height), "#fafafa")
    draw = ImageDraw.Draw(sheet)
    for index, packet in enumerate(parts):
        x0 = MARGIN + index * PITCH

        def rectangle(left, top, right, bottom, color):
            x, y = x0 + left, MARGIN + top
            draw.rectangle((x * module, y * module, (x0 + right) * module - 1,
                            (MARGIN + bottom) * module - 1), fill=color)

        for x, y, color in (
            (FINDER_LEFT, FINDER_LEFT, "#e92caa"),
            (FINDER_RIGHT, FINDER_LEFT, "#16bde8"),
            (FINDER_LEFT, FINDER_BOTTOM, "#25c05b"),
        ):
            rectangle(x - 2, y - 2, x + 2, y + 2, color)
        for position in range(COLS * ROWS):
            if packet[position // 8] & (0x80 >> (position % 8)):
                y, x = divmod(position, COLS)
                rectangle(DATA_OFFSET + x, DATA_OFFSET + y, DATA_OFFSET + x + 1, DATA_OFFSET + y + 1, "#171717")
    buffer = io.BytesIO()
    sheet.save(buffer, "PNG")
    return buffer.getvalue()


def finder_components(mask):
    _, _, stats, centers = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return [
        (float(x), float(y), int(width), int(height))
        for (_, _, width, height, area), (x, y) in zip(stats[1:], centers[1:], strict=True)
        if area >= 12 and width >= 3 and height >= 3
    ]


def find_tiles(pixels):
    r, g, b = pixels.transpose(2, 0, 1)
    magenta = finder_components((r > 145) & (g < 115) & (b > 105))
    cyan = finder_components((r < 110) & (g > 130) & (b > 160))
    green = finder_components((r < 110) & (g > 130) & (b < 140))
    if max(map(len, (magenta, cyan, green))) > 4 * (MAX_SHARDS + 1):
        raise ValueError("Trop de repères candidats")
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    for x, y, mark_width, mark_height in magenta:
        horizontal = [other for other in cyan if other[0] > x and abs(other[1] - y) <= mark_height / 2]
        vertical = [other for other in green if other[1] > y and abs(other[0] - x) <= mark_width / 2]
        if not horizontal or not vertical:
            continue
        cx, _, _, _ = min(horizontal, key=lambda mark: mark[0])
        _, gy, _, _ = min(vertical, key=lambda mark: mark[1])
        sx = (cx - x) / (FINDER_RIGHT - FINDER_LEFT)
        sy = (gy - y) / (FINDER_BOTTOM - FINDER_LEFT)
        if not (1.5 <= sx <= 14 and 1.5 <= sy <= 14 and 2.2 * sx <= mark_width <= 5.8 * sx
                and 2.2 * sy <= mark_height <= 5.8 * sy):
            continue
        xs = np.rint(x + (DATA_OFFSET + np.arange(COLS) + 0.5 - FINDER_LEFT) * sx).astype(int)
        ys = np.rint(y + (DATA_OFFSET + np.arange(ROWS) + 0.5 - FINDER_LEFT) * sy).astype(int)
        if 0 <= xs[0] <= xs[-1] < width and 0 <= ys[0] <= ys[-1] < height:
            yield np.packbits(gray[np.ix_(ys, xs)] < 125, bitorder="big").tobytes()


def decode(blob):
    if len(blob) > gf.MAX_FILE:
        raise ValueError("Fichier trop volumineux")
    with Image.open(io.BytesIO(blob), formats=["PNG", "JPEG", "WEBP"]) as image:
        gf.rgba_length(*image.size)
        pixels = np.asarray(image.convert("RGB"))
    groups = {}
    for tile in find_tiles(pixels):
        magic, index, count, length, identifier, crc = HEADER.unpack_from(tile)
        shard = tile[HEADER.size:]
        if (magic != b"GFC1" or not 1 <= count <= MAX_SHARDS or index > count
                or not (count - 1) * SHARD_BYTES < length <= count * SHARD_BYTES
                or zlib.crc32(shard) != crc):
            continue
        group = groups.setdefault((count, length, identifier), {})
        if index in group and group[index] != shard:
            raise ValueError("Tuiles contradictoires pour un même index")
        group[index] = shard
    candidates = []
    for (count, length, identifier), parts in groups.items():
        present = tuple(sorted(parts))
        missing = [index for index in range(count) if index not in parts]
        repaired = None
        if missing:
            if len(missing) != 1 or count not in parts:
                continue
            repaired = missing[0]
            restored = parts[count]
            for index in present:
                if index != count:
                    restored = gf.xor_frame(restored, parts[index])
            parts[repaired] = restored
        payload = b"".join(parts[index] for index in range(count))[:length]
        if bytes.fromhex(gf.digest(payload))[:8] != identifier:
            continue
        motion, poster_hash = gf.read_archive(payload)
        if bytes.fromhex(gf.digest(motion.frames[0])) == poster_hash:
            candidates.append(Readout(motion, present, count, repaired))
    if len(candidates) != 1:
        observed = max((len(group) for group in groups.values()), default=0)
        raise ValueError(f"Capsule non récupérable ({observed} tuiles valides au maximum)")
    return candidates[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["pack", "unpack"])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        source = args.source.read_bytes()
        if args.command == "pack":
            _, _, motion = gf.decoded_png(source)
            if motion is None:
                raise ValueError("Un APNG est requis")
            output = encode(motion)
        else:
            output = gf.apng(decode(source).motion, sparse=True)
        args.output.write_bytes(output)
    except (ValueError, KeyError, OSError, SyntaxError, EOFError, zlib.error, struct.error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
