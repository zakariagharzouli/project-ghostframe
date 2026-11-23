"""Evaluate the frozen codec on a source corpus and a separate JPEG pipeline."""

import argparse
import hashlib
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import cv2
import numpy as np
import zxingcpp as zx
from PIL import Image

import benchmark as bench


DATASET = "likaixin/ScreenSpot-Pro"
REVISION = "210e78d3844251110bff86c95835ebd37a6930fa"
SEED = "ghostframe-replay-holdout-1"
FOLLOWUP_SEED = "ghostframe-replay-holdout-2"
APPS = (
    "android_studio_macos", "blender_windows", "davinci_macos", "eviews_windows",
    "excel_macos", "linux_common_linux", "matlab_macos", "photoshop_windows",
    "powerpoint_windows", "pycharm_macos", "vscode_macos", "windows_common_windows",
)
FORMATS = bench.FORMATS | {
    "qr": (zx.BarcodeFormat.QRCode, "LMQH", range(1, 16)),
    "dmre": (zx.BarcodeFormat.DataMatrix, (None,), range(25, 49)),
}


def get_file(relative, cache):
    url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{quote(relative)}"
    target = cache / (hashlib.sha256(relative.encode()).hexdigest() + Path(relative).suffix)
    if not target.is_file():
        with urlopen(url, timeout=30) as response:
            data = response.read(32_000_001)
        if len(data) > 32_000_000:
            raise ValueError(f"Source file too large: {relative}")
        target.write_bytes(data)
    return target


def normalize_dimensions(width, height):
    ratio = min(1, 1600 / width, 1440 / height)
    return max(1, round(width * ratio)), max(1, round(height * ratio))


def selected(app, cache, *, seed=SEED, exclude=()):
    source = f"annotations/{app}.json"
    entries = json.loads(get_file(source, cache).read_text(encoding="utf-8"))
    candidates = defaultdict(list)
    for row in entries:
        if f"images/{row['img_filename']}" in exclude:
            continue
        w, h = row["img_size"]
        width, height = normalize_dimensions(w, h)
        poster_width = max(width, 928)
        offset = (poster_width - 928) // 2
        x0, y0, x1, y1 = row["bbox"]
        x = int((x0 + x1) / 2 * width / w) + (poster_width - width) // 2
        y = int((y0 + y1) / 2 * height / h)
        if offset + 232 <= x < offset + 696 and 32 <= y < height:
            candidates[row["img_filename"]].append((row, x, y))
    if not candidates:
        raise ValueError(f"No eligible screenshot: {app}")
    image = min(candidates, key=lambda path: hashlib.sha256(f"{seed}/{app}/{path}".encode()).digest())
    rows = sorted(candidates[image], key=lambda entry: entry[0]["id"])[:3]
    image_path = f"images/{image}"
    cached = get_file(image_path, cache)
    screenshot = cv2.imread(str(cached), cv2.IMREAD_COLOR)
    original_size = tuple(rows[0][0]["img_size"])
    if screenshot is None or screenshot.shape[1::-1] != original_size:
        raise ValueError(f"Image size differs from the original annotation: {image_path}")
    width, height = normalize_dimensions(*original_size)
    screenshot = cv2.resize(screenshot, (width, height), interpolation=cv2.INTER_AREA)
    poster = Image.new("RGB", (max(width, 928), height), "white")
    poster.paste(Image.fromarray(cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)), ((poster.width - width) // 2, 0))
    steps = [{"x": x, "y": y, "duration": 700 + index * 200,
              "note": row["instruction"].encode("utf-8")[:72].decode("utf-8", errors="ignore")}
             for index, (row, x, y) in enumerate(rows)]
    manifest = {
        "app": app, "path": image_path, "sha256": hashlib.sha256(cached.read_bytes()).hexdigest(),
        "source_size": original_size, "poster_size": poster.size,
        "annotation_ids": [row["id"] for row, _, _ in rows],
    }
    return (app, poster, steps), manifest


def encode_jpeg(pixels, quality):
    success, data = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise RuntimeError("OpenCV JPEG encoding failed")
    return data


def carrier(poster, band):
    color = cv2.cvtColor(np.asarray(poster), cv2.COLOR_RGB2BGR)
    stripe = cv2.cvtColor(np.asarray(band), cv2.COLOR_GRAY2BGR)
    return encode_jpeg(np.concatenate((color, stripe)), 92)


def transform(source, box, percent, quality, gray):
    x0, y0, x1, y1 = box
    bgr = cv2.imdecode(source, cv2.IMREAD_COLOR)[y0:y1, x0:x1]
    if percent != 100:
        size = round(bgr.shape[1] * percent / 100), round(bgr.shape[0] * percent / 100)
        bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
    if quality is None:
        luminance = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    else:
        raster = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if gray else bgr
        luminance = cv2.imdecode(encode_jpeg(raster, quality), cv2.IMREAD_GRAYSCALE)
    h, w = luminance.shape
    top = max(0, h - bench.SCAN_ROWS)
    return (w, h), top, Image.fromarray(luminance[top:])


def cases(width, height, offset):
    for case in bench.cases(width, height, offset):
        if case[0] in {"original92", "gris-gauche-50-q65", "sans-bande"} or case[2] in {63, 50, 40}:
            yield case


def paired_by_screenshot(fixtures):
    outcomes = []
    for fixture in fixtures:
        cases = bench.paired_blind([fixture])
        delta = (cases["gfs2_only"] - cases["reference_only"]) / len(fixture["cases"])
        outcomes.append({"app": fixture["name"], **cases, "gain": delta})
    gains = np.array([row["gain"] for row in outcomes])
    # One sampled unit is an entire screenshot and all of its transformations.
    rng = np.random.default_rng(20261123)
    means = rng.choice(gains, (20_000, len(gains))).mean(axis=1)
    return {
        "applications": outcomes, "observed_gain": float(gains.mean()),
        "bootstrap_95_percent": np.quantile(means, [.025, .975]).tolist(),
        "positive": int(np.count_nonzero(gains > 0)),
        "equal": int(np.count_nonzero(gains == 0)),
        "negative": int(np.count_nonzero(gains < 0)),
    }


def known_grid_tiles(band, poster_size, case, received):
    # Compare sampled bits with the transmitted bits. This is diagnostic only:
    # a real decoder has neither the known transform nor the transmitted bits.
    width, height = poster_size
    _, box, *_ = case
    x0, y0, x1, y1 = box
    (received_width, received_height), top, strip = received
    sx, sy = received_width / (x1 - x0), received_height / (y1 - y0)
    offset = (width - 928) // 2
    pixels = np.asarray(strip)
    rows = band.shape[0] // 4 - 6
    sampled_tiles = []
    for tile in range(4):
        left = offset + tile * 232
        if left < x0 or left + 232 > x1 or height < y0 or height + band.shape[0] > y1:
            continue
        cols = left + 22 + 4 * np.arange(48)
        lines = 14 + 4 * np.arange(rows)
        x = (cols - x0) * sx
        y = (height + lines - y0) * sy - top
        if min(x) < 0 or min(y) < 0 or max(x) >= strip.width or max(y) >= strip.height:
            continue
        expected = band[np.ix_(lines, cols)] < 128
        nearest = pixels[np.ix_(y.astype(int), x.astype(int))] < 128
        # cv2.remap uses integer pixel centers, so subtract half a pixel to convert.
        gx, gy = np.meshgrid((x - .5).astype(np.float32), (y - .5).astype(np.float32))
        linear = cv2.remap(pixels, gx, gy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) < 128
        sampled_tiles.append({"tile": tile, "bit_errors_nearest": int(np.count_nonzero(nearest != expected)),
                              "bit_errors_linear": int(np.count_nonzero(linear != expected))})
    return sampled_tiles


def diagnose(result, samples):
    diagnostics = []
    with bench.Codec() as codec:
        for sample, fixture in zip(samples, result["fixtures"], strict=True):
            name, poster, steps = sample
            width, height = poster.size
            rendered = codec.call("render", width=width, height=height, steps=steps)
            payload = bench.binary(rendered["payload"])
            band = Image.frombytes("L", (width, rendered["rows"]), bench.binary(rendered["band"]))
            image = carrier(poster, band)
            definitions = {case[0]: case for case in cases(width, height + band.height, (width - 928) // 2)}
            for entry in fixture["cases"]:
                outcome = entry["max_click_error_px"]
                if outcome["ghostframe"] is not None or entry["case"] == "sans-bande":
                    continue
                case = definitions[entry["case"]]
                received = transform(image, *case[1:])
                tiles = known_grid_tiles(np.asarray(band), poster.size, case, received)
                interpolation = bench.ghost_result(codec, received, payload, steps, case[1], interpolate=True)
                diagnostics.append({"app": name, "case": case[0], "tiles": tiles,
                                    "bilinear_click_error_px": interpolation,
                                    "reference_won": any(value is not None and value <= 2 for key, value in outcome.items()
                                                         if key != "ghostframe")})
    return diagnostics


def main(output, cache, original=None):
    cache.mkdir(parents=True, exist_ok=True)
    seed = FOLLOWUP_SEED if original else SEED
    previous = json.loads(original.read_text(encoding="utf-8"))["images"] if original else []
    excluded = {item["path"] for item in previous}
    with ThreadPoolExecutor(max_workers=4) as pool:
        selections = list(pool.map(lambda app: selected(app, cache, seed=seed, exclude=excluded), APPS))
    samples, manifest = zip(*selections)
    if len({item["sha256"] for item in manifest}) != len(APPS):
        raise ValueError("Two applications selected the same source bytes")
    if {item["sha256"] for item in manifest}.intersection(item["sha256"] for item in previous):
        raise ValueError("Follow-up data overlaps the original")
    result = {
        "dataset": DATASET, "revision": REVISION, "selection_seed": seed, "images": manifest,
        "pipeline": "OpenCV JPEG/INTER_AREA", "versions": {name: version(name) for name in
            ("Pillow", "numpy", "zxing-cpp", "opencv-python-headless")}, "fixtures": [],
    }
    bench.run_benchmark(output, result, samples, carrier, transform, cases, FORMATS, retry_bilinear=bool(original))
    result["paired_by_screenshot"] = paired_by_screenshot(result["fixtures"])
    if not original:
        result["failed_tile_diagnostics"] = diagnose(result, samples)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result["paired_by_screenshot"].items() if key != "applications"},
                     indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("run/replay/screenspot-cache"))
    parser.add_argument("--out", type=Path, default=Path("run/replay/holdout.json"))
    parser.add_argument("--followup-from", type=Path, metavar="ORIGINAL_REPORT")
    args = parser.parse_args()
    main(args.out, args.cache, args.followup_from)
