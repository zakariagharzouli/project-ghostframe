"""Compare Replay's production codec with fragmented QR and rMQR at equal area."""

import argparse
import base64
import io
import json
import math
import struct
import subprocess
import zlib
from collections import defaultdict
from dataclasses import dataclass
from functools import reduce
from importlib.metadata import version
from pathlib import Path
from statistics import median

import numpy as np
import zxingcpp as zx
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHARD_HEADER = struct.Struct(">IHB")
SCAN_ROWS = 96
RULER_TOLERANCE = 2
RESAMPLERS = {"lanczos": Image.Resampling.LANCZOS, "bicubic": Image.Resampling.BICUBIC}
FORMATS = {
    "qr": (zx.BarcodeFormat.QRCode, "LMQH", range(1, 9)),
    "rmqr": (zx.BarcodeFormat.RMQRCode, "MH", range(1, 33)),
}


class Codec:
    def __enter__(self):
        self.proc = subprocess.Popen(["node", str(HERE / "benchmark-codec.cjs")], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True, encoding="utf-8")
        return self

    def __exit__(self, *_):
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.proc.wait(timeout=10)

    def call(self, operation, **args):
        self.proc.stdin.write(json.dumps({"operation": operation, **args}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("Node codec stopped unexpectedly")
        response = json.loads(line)
        if "error" in response:
            raise ValueError(response["error"])
        return response["result"]


def binary(data):
    return base64.b64decode(data, validate=True)


def ascii_packet(data):
    return base64.b64encode(data).decode("ascii")


def xor(shards, size):
    value = reduce(int.__xor__, (int.from_bytes(part, "big") for part in shards), 0)
    return value.to_bytes(size, "big")


def fragment(payload, count):
    size = math.ceil(len(payload) / count)
    padded = payload.ljust(count * size, b"\0")
    pieces = [padded[i:i + size] for i in range(0, len(padded), size)]
    pieces.append(xor(pieces, size))
    return [SHARD_HEADER.pack(zlib.crc32(payload), len(payload), (count << 4) | index) + piece
            for index, piece in enumerate(pieces)]


@dataclass(frozen=True)
class Layout:
    key: str
    format: object
    module: int
    strip: Image.Image
    corners: tuple


def raster_symbol(packet, fmt, ecc, variant):
    barcode = zx.create_barcode(packet, fmt, version=variant, ec_level=ecc)
    if barcode.ec_level != ecc:
        raise ValueError(f"Requested ECC {ecc}, got {barcode.ec_level}")
    return np.asarray(zx.write_barcode_to_image(barcode))


def qr_layouts(payload, width, body_height, band_height, strip_width):
    offset = (width - strip_width) // 2
    for family, (fmt, levels, versions) in FORMATS.items():
        for count in (2, 3, 5):
            packets = fragment(payload, count)
            slot_width = strip_width // len(packets)
            for ecc in levels:
                choices = []
                for variant in versions:
                    try:
                        h, w = raster_symbol(packets[0], fmt, ecc, variant).shape
                    except (ValueError, RuntimeError):
                        continue
                    scale = min(band_height // h, slot_width // w)
                    if scale:
                        choices.append((scale, h * w, -variant, h, w))
                if not choices:
                    continue
                largest = max(choices)
                smallest = min(choice for choice in choices if choice[0] == largest[0])
                for scale, _, chosen, h, w in sorted({smallest, largest}):
                    variant = -chosen
                    quiet = (4 if family == "qr" else 2) * scale
                    strip = Image.new("L", (width, band_height), 255)
                    corners = []
                    for index, packet in enumerate(packets):
                        modules = raster_symbol(packet, fmt, ecc, variant)
                        assert modules.shape == (h, w)
                        symbol = Image.fromarray(np.where(modules < 128, 16, 255).astype(np.uint8))
                        pixels = symbol.resize((w * scale, h * scale), Image.Resampling.NEAREST)
                        left = offset + ((2 * index + 1) * strip_width // len(packets) - pixels.width) // 2
                        top = (band_height - pixels.height) // 2
                        assert offset <= left and left + pixels.width <= offset + strip_width
                        strip.paste(pixels, (left, top))
                        x0, x1 = left + quiet, left + pixels.width - quiet
                        y0, y1 = body_height + top + quiet, body_height + top + pixels.height - quiet
                        corners.append(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
                    yield Layout(f"{family}-{count}-{ecc}-v{variant}-{scale}px", fmt, scale, strip, tuple(corners))


def decode_fragments(symbols):
    groups = defaultdict(dict)
    for payload, position in symbols:
        if len(payload) <= SHARD_HEADER.size:
            continue
        checksum, length, descriptor = SHARD_HEADER.unpack_from(payload)
        count, index = descriptor >> 4, descriptor & 15
        shard = payload[SHARD_HEADER.size:]
        if not (2 <= count <= 5 and index <= count and 1 <= length <= 243
                and len(shard) == math.ceil(length / count)):
            continue
        groups[(checksum, length, count)][index] = shard, position

    for (checksum, length, count), pieces in groups.items():
        missing = [i for i in range(count) if i not in pieces]
        if len(missing) > 1 or (missing and count not in pieces):
            continue
        ordered = [pieces[i][0] if i in pieces else None for i in range(count)]
        if missing:
            ordered[missing[0]] = xor((part for part, _ in pieces.values()), len(pieces[count][0]))
        payload = b"".join(ordered)[:length]
        if zlib.crc32(payload) == checksum:
            yield payload, {index: position for index, (_, position) in pieces.items()}


def locate_qr(strip, top, layout):
    # Give the reference readers their native sampling plus two fixed upsampling passes.
    symbols = {}
    for scale, mode in ((1, None), (2, Image.Resampling.NEAREST), (2, Image.Resampling.BICUBIC)):
        image = strip if scale == 1 else strip.resize((strip.width * scale, strip.height * scale), mode)
        for code in zx.read_barcodes(image, formats=layout.format, try_rotate=False, try_downscale=False):
            points = code.position
            corners = tuple((p.x / scale, top + p.y / scale) for p in
                            (points.top_left, points.top_right, points.bottom_right, points.bottom_left))
            symbols.setdefault(code.bytes, corners)
        reads = list(decode_fragments(symbols.items()))
        if len(reads) == 1:
            return reads[0]
    return None


def fit_axis(original, rendered):
    base = np.asarray(original)
    seen = np.asarray(rendered)
    slope = float(np.dot(base - base.mean(), seen - seen.mean()) / np.sum((base - base.mean()) ** 2))
    return slope, float(seen.mean() - slope * base.mean())


def qr_geometry(positions, layout):
    source = [corner for index in positions for corner in layout.corners[index]]
    observed = [corner for corners in positions.values() for corner in corners]
    original_x, original_y = zip(*source)
    measured_x, measured_y = zip(*observed)
    sx, left = fit_axis(original_x, measured_x)
    sy, top = fit_axis(original_y, measured_y)
    # The same near-uniform prior as the Ghostframe reader, applied to decoded corners.
    if abs(sx - sy) * (max(original_y) - min(original_y)) <= 1.1:
        sy = sx
        top = (sum(measured_y) - sy * sum(original_y)) / len(source)
    return sx, sy, left, top


def jpeg(image, quality):
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=quality)
    return stream.getvalue()


def paint_interface(width, height, style):
    palettes = (("#e6ebf4", "#242e4d", "#ffffff", "#1c2943", "#395dbb"),
                ("#161821", "#303449", "#252735", "#eeeeef", "#8040ed"))
    page, header, card, text, action = palettes[style % 2]
    image = Image.new("RGB", (width, height), page)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 59), fill=header)
    font = ImageFont.load_default(size=20)
    draw.text((24, 17), "Residual Labs · banc de support", font=font, fill="#f2f3ff")
    draw.rounded_rectangle((56, 95, width - 58, height - 33), 12, fill=card)
    draw.text((84, 121), ("Import", "Synchronisation", "Paramètres", "Export")[style], font=font, fill=text)
    for number in range(5):
        y = 175 + number * (height - 240) // 5
        draw.rectangle((82, y, width - 84, y + 2), fill=header)
        draw.text((88, y + 12), f"Tâche {number + 1} — diagnostic", font=font, fill=text)
        draw.rounded_rectangle((width - 228, y + 8, width - 92, y + 38), 4, fill=action)
        draw.text((width - 218, y + 10), "Détails", font=font, fill="#ffffff")
    return image


def fixtures():
    for name, count, notes, width, height, style in (
        ("court", 1, ("",), 928, 540, 0),
        ("demo", 3, ("Choisir commandes.csv", "Lancer l’import", "L’erreur 42 apparaît"), 1120, 650, 1),
        ("moyen", 5, ("Ouvrir les paramètres", "Choisir la copie locale", "Attendre la synchronisation",
                     "Afficher les détails", "Copier le message d’erreur"), 1360, 800, 2),
        ("plein", 3, ("a" * 96, "b" * 96, "c" * 28), 1120, 720, 3),
    ):
        steps = [dict(x=(width * (38 + index * 6)) // 100, y=(height * (26 + index * 12)) // 100,
                      duration=700 + index * 200, note=notes[index]) for index in range(count)]
        yield name, paint_interface(width, height, style), steps


def cases(width, height, offset):
    yield "original92", (0, 0, width, height), 100, None, False
    for direction, box in (
        ("intact", (0, 0, width, height)), ("gauche", (offset + 232, 32, width, height)),
        ("droite", (0, 32, offset + 696, height)),
    ):
        for percent in (100, 63, 50, 40, 35):
            for quality in (65, 30):
                yield f"{direction}-{percent}-q{quality}", box, percent, quality, False
    yield "gris-gauche-50-q65", (offset + 232, 32, width, height), 50, 65, True
    yield "sans-bande", (0, 0, width, height - 88), 100, 65, False


def carrier(poster, band):
    image = Image.new("RGB", (poster.width, poster.height + band.height), "white")
    image.paste(poster, (0, 0))
    image.paste(band, (0, poster.height))
    return jpeg(image, 92)


def transform(source, box, percent, quality, gray, resample):
    with Image.open(io.BytesIO(source)) as initial:
        image = initial.crop(box)
        if percent != 100:
            dimensions = (round(image.width * percent / 100), round(image.height * percent / 100))
            image = image.resize(dimensions, resample)
        if quality is not None:
            image = Image.open(io.BytesIO(jpeg(image.convert("L") if gray else image, quality)))
        image = image.convert("L")
    top = max(0, image.height - SCAN_ROWS)
    return image.size, top, image.crop((0, top, image.width, image.height))


def click_error(geometry, steps, image_size, box):
    sx, sy, left, top = geometry
    crop_x, crop_y, right, bottom = box
    true_x, true_y = image_size[0] / (right - crop_x), image_size[1] / (bottom - crop_y)
    distances = []
    for step in steps:
        x, y = step["x"] + .5, step["y"] + .5
        if crop_x <= x < right and crop_y <= y < bottom:
            distances.append(math.hypot(sx * x + left - true_x * (x - crop_x),
                                        sy * y + top - true_y * (y - crop_y)))
    return round(max(distances), 5) if distances else None


def ghost_result(codec, data, payload, steps, box):
    size, top, strip = data
    result = codec.call("read", width=strip.width, height=strip.height, top=top, raster=ascii_packet(strip.tobytes()))
    if not result:
        return None
    if binary(result["payload"]) != payload:
        raise AssertionError("Ghostframe read an unexpected payload")
    return click_error(tuple(result[field] for field in ("sx", "sy", "left", "top")), steps, size, box)


def qr_result(layout, data, payload, steps, box):
    size, top, strip = data
    result = locate_qr(strip, top, layout)
    if not result:
        return None
    recovered, positions = result
    if recovered != payload:
        raise AssertionError(f"{layout.key} read an unexpected payload")
    return click_error(qr_geometry(positions, layout), steps, size, box)


def known_grid_qr(layout, data, box):
    # Give the reference decoder the exact crop and scale. This probes symbol
    # recovery separately from detection and the accuracy of the recovered geometry.
    (width, height), top, strip = data
    crop_x, crop_y, right, bottom = box
    scale_x, scale_y = width / (right - crop_x), height / (bottom - crop_y)
    image = np.asarray(strip)
    symbols = {}
    for (x0, y0), _, (x1, y1), _ in layout.corners:
        if x0 < crop_x or y0 < crop_y or x1 > right or y1 > bottom:
            continue
        x = (np.arange(x0 + layout.module / 2, x1, layout.module) - crop_x) * scale_x
        y = (np.arange(y0 + layout.module / 2, y1, layout.module) - crop_y) * scale_y - top
        if x.min() < 0 or y.min() < 0 or x.max() >= strip.width or y.max() >= strip.height:
            continue
        for sampling in ("nearest", "linear"):
            if sampling == "nearest":
                pixels = image[np.ix_(y.astype(int), x.astype(int))]
            else:
                x0b = np.clip(np.floor(x - .5).astype(int), 0, strip.width - 1)
                y0b = np.clip(np.floor(y - .5).astype(int), 0, strip.height - 1)
                x1b = np.minimum(x0b + 1, strip.width - 1)
                y1b = np.minimum(y0b + 1, strip.height - 1)
                fx = np.clip(x - .5 - x0b, 0, 1)
                fy = np.clip(y - .5 - y0b, 0, 1)[:, None]
                upper = image[np.ix_(y0b, x0b)] * (1 - fx) + image[np.ix_(y0b, x1b)] * fx
                lower = image[np.ix_(y1b, x0b)] * (1 - fx) + image[np.ix_(y1b, x1b)] * fx
                pixels = upper * (1 - fy) + lower * fy
            module_pixels = np.where(pixels < 128, 0, 255).astype(np.uint8)
            fitted = np.repeat(np.repeat(np.pad(module_pixels, 4, constant_values=255), 3, 0), 3, 1)
            symbol = zx.read_barcode(fitted, formats=layout.format, try_rotate=False,
                                     try_downscale=False, is_pure=True)
            if symbol:
                symbols[symbol.bytes] = None
    return [payload for payload, _ in decode_fragments(symbols.items())]


def score(errors):
    return {"decoded": sum(error is not None for error in errors),
            "within_2px": sum(error is not None and error <= RULER_TOLERANCE for error in errors)}


def main(output, resampler):
    result = {"resampler": resampler,
              "versions": {name: version(name) for name in ("Pillow", "numpy", "zxing-cpp")}, "fixtures": []}
    resample = RESAMPLERS[resampler]
    with Codec() as codec:
        for name, poster, steps in fixtures():
            w, h = poster.size
            encoded = codec.call("render", width=w, height=h, steps=steps)
            payload = binary(encoded["payload"])
            height, width = encoded["rows"], encoded["stripWidth"]
            band = Image.frombytes("L", (w, height), binary(encoded["band"]))
            ours = carrier(poster, band)
            layouts = tuple((layout, carrier(poster, layout.strip))
                            for layout in qr_layouts(payload, w, h, height, width))
            assert {layout.key.split("-")[0] for layout, _ in layouts} == set(FORMATS)
            fixture = {"name": name, "payload_bytes": len(payload), "band": [width, height],
                       "jpeg_bytes": {"ghostframe": len(ours), **{layout.key: len(data) for layout, data in layouts}},
                       "cases": []}
            for label, box, pct, quality, gray in cases(w, h + height, (w - width) // 2):
                args = (box, pct, quality, gray, resample)
                measurements = {"ghostframe": ghost_result(codec, transform(ours, *args), payload, steps, box)}
                guided = {}
                for layout, image in layouts:
                    sample = transform(image, *args)
                    measurements[layout.key] = qr_result(layout, sample, payload, steps, box)
                    reads = known_grid_qr(layout, sample, box)
                    if any(read != payload for read in reads):
                        raise AssertionError(f"{layout.key} read an unexpected payload from the known grid")
                    guided[layout.key] = bool(reads)
                if label == "original92":
                    assert measurements["ghostframe"] is not None
                    for family in FORMATS:
                        assert any(k.startswith(family + "-") and v is not None for k, v in measurements.items())
                        assert any(k.startswith(family + "-") and v for k, v in guided.items())
                assert label != "sans-bande" or all(value is None for value in measurements.values())
                assert label != "sans-bande" or not any(guided.values())
                fixture["cases"].append({"case": label, "max_click_error_px": measurements,
                                         "known_grid_qr_decoded": guided})
            result["fixtures"].append(fixture)
            print(name, len(payload), f"{width}×{height}", len(layouts), flush=True)
    result["summary"] = summary(result["fixtures"])
    result["known_grid_summary"] = {
        family: sum(any(key.startswith(family + "-") and value
                        for key, value in case["known_grid_qr_decoded"].items())
                    for fixture in result["fixtures"] for case in fixture["cases"])
        for family in FORMATS
    }
    result["paired_blind"] = paired_blind(result["fixtures"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"blind": result["summary"], "known_grid": result["known_grid_summary"]},
                     ensure_ascii=False, indent=2))


def summary(results):
    methods = ("ghostframe", "qr", "rmqr")
    comparison = {method: [] for method in methods}
    for fixture in results:
        best = {method: [] for method in methods}
        for case in fixture["cases"]:
            values = case["max_click_error_px"]
            for method in methods:
                valid = [value for key, value in values.items() if key.split("-")[0] == method and value is not None]
                best[method].append(min(valid, default=None))
        for method in methods:
            comparison[method].extend(best[method])
        fixture["summary"] = {method: score(best[method]) for method in methods}
    return {method: {**score(errors), "total": len(errors),
                     "median_max_error_px": round(median(x for x in errors if x is not None), 3)
                     if any(x is not None for x in errors) else None}
            for method, errors in comparison.items()}


def paired_blind(fixtures):
    pairs = {"both": 0, "gfs2_only": 0, "reference_only": 0, "neither": 0}
    for fixture in fixtures:
        for case in fixture["cases"]:
            values = case["max_click_error_px"]
            ghost = values["ghostframe"] is not None and values["ghostframe"] <= RULER_TOLERANCE
            reference = any(error is not None and error <= RULER_TOLERANCE
                            for name, error in values.items() if name != "ghostframe")
            key = {(True, True): "both", (True, False): "gfs2_only", (False, True): "reference_only",
                   (False, False): "neither"}[(ghost, reference)]
            pairs[key] += 1
    return pairs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("run/replay-benchmark.json"))
    parser.add_argument("--resample", choices=RESAMPLERS, default="lanczos")
    args = parser.parse_args()
    main(args.out, args.resample)
