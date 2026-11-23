"""Create the positive and negative JPEG controls from the editor example."""

import argparse
from pathlib import Path

from PIL import Image, ImageOps


def reduce_half(image):
    return image.resize((image.width // 2, image.height // 2), Image.Resampling.LANCZOS)


def compare(compact, legacy, output):
    output.mkdir(parents=True, exist_ok=True)
    for version, source in (("v1", legacy), ("v2", compact)):
        with Image.open(source) as image:
            for name, region in (("intact", image), ("crop", image.crop((328, 32, image.width, image.height)))):
                for percent in (63, 50, 45, 40):
                    dimensions = round(region.width * percent / 100), round(region.height * percent / 100)
                    scaled = region.resize(dimensions, Image.Resampling.LANCZOS)
                    for quality in (85, 65, 45, 30):
                        scaled.save(output / f"{version}-{name}-{percent}-{quality}.jpg", quality=quality)


def main(source, output):
    with Image.open(source) as image:
        if image.format != "JPEG" or image.size not in {(1120, 706), (1120, 738)}:
            raise ValueError("Exportez l’exemple Ghostframe à 1 120 pixels de large.")
        width, height = image.size
        cropped = image.crop((328, 32, width, height))
        cases = {
            "jpeg65": image,
            "resize50": reduce_half(image),
            "resize63": image.resize((706, round(height * .63)), Image.Resampling.LANCZOS),
            "crop50": reduce_half(cropped),
            "gray-crop50": ImageOps.grayscale(reduce_half(cropped)),
            "two-tiles-lost": reduce_half(image.crop((560, 0, width, height))),
            "thumbnail150": image.resize((150, round(height * 150 / width)), Image.Resampling.LANCZOS),
        }
        output.mkdir(parents=True, exist_ok=True)
        for name, result in cases.items():
            path = output / f"ghostframe-{name}.jpg"
            result.save(path, quality=65)
            print(f"{name} {result.width}x{result.height} {path.stat().st_size} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--compare", type=Path, metavar="LEGACY_JPEG")
    args = parser.parse_args()
    main(args.source, args.output)
    if args.compare:
        compare(args.source, args.compare, args.output / "replay-matrix")
