"""Compare an authorized upload and the bytes and screenshots returned by its client."""

import argparse
import json
from collections import Counter
from pathlib import Path

from PIL import Image

import ghostframe as gf
from pipelines import FORMATS, changes, describe


def capture_hash(path, box):
    with Image.open(path, formats=["PNG"]) as image:
        gf.rgba_length(*image.size)
        if box:
            x, y, width, height = box
            if min(x, y) < 0 or min(width, height) <= 0 or x + width > image.width or y + height > image.height:
                raise ValueError(f"Zone hors capture dans {path.name}")
            image = image.crop((x, y, x + width, y + height))
        return list(image.size), gf.digest(image.convert("RGBA").tobytes())


def compare(original_path, delivered_path, receipt, capture_root):
    original, source = describe(original_path.read_bytes())
    delivered, target = describe(delivered_path.read_bytes())
    expected_mime = FORMATS[delivered["format"]][1]
    samples = []
    for frame in receipt.get("captures", []):
        size, fingerprint = capture_hash(capture_root / frame["file"], receipt.get("box"))
        samples.append({"elapsed_ms": frame["elapsed_ms"], "size": size, "sha256": fingerprint})
    times = [frame["elapsed_ms"] for frame in samples]
    if any(not isinstance(value, int) or value < 0 for value in times) or times != sorted(set(times)):
        raise ValueError("Horodatages entiers, positifs et strictement croissants requis")
    if len({tuple(frame["size"]) for frame in samples}) > 1:
        raise ValueError("Toutes les régions capturées doivent avoir la même taille")
    observed = Counter(frame["sha256"] for frame in samples)
    original_motion, delivered_motion = original["motion"], delivered["motion"]
    same = changes(original, delivered, source, target)
    expected_frames = set(delivered_motion["frames"]) if delivered_motion else set()
    exact_render = len(observed) > 1 and set(observed) == expected_frames and all(
        frame["size"] == delivered["size"] for frame in samples
    )
    classified = "indéterminé"
    accepted = receipt.get("accepted_as_png")
    if accepted is False:
        classified = "échec"
    elif original["format"] == "PNG" and accepted is True and receipt.get("standard_client") is True:
        if receipt.get("delivery_mime") == expected_mime and exact_render and same["same_motion"]:
            classified = "succès"
        elif original_motion and delivered_motion is None and len(observed) == 1 and len(times) >= 3:
            delays = original_motion["delays_ms"]
            if all(delay > 0 for delay in delays) and times[-1] - times[0] >= 2 * sum(delays):
                classified = "échec"
    return {
        "receipt": receipt, "before": original, "after": delivered, "transform": same,
        "capture_sha256_counts": dict(observed), "samples": samples,
        "render_exact": exact_render, "native_result": classified,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("delivered", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        result = compare(args.original, args.delivered, receipt, args.receipt.parent)
    except (ValueError, KeyError, TypeError, OSError, SyntaxError, EOFError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
