"""Create the positive and negative JPEG controls from the editor example."""

import argparse
from pathlib import Path

from PIL import Image, ImageOps


def reduce_half(image):
    return image.resize((image.width // 2, image.height // 2), Image.Resampling.LANCZOS)


def main(source, output):
    with Image.open(source) as image:
        if image.format != "JPEG" or image.size != (1120, 738):
            raise ValueError("Exportez l’exemple Ghostframe de 1 120 × 738 pixels.")
        width, height = image.size
        cropped = image.crop((328, 32, width, height))
        cases = {
            "jpeg65": image,
            "resize50": reduce_half(image),
            "crop50": reduce_half(cropped),
            "gray-crop50": ImageOps.grayscale(reduce_half(cropped)),
            "two-tiles-lost": reduce_half(image.crop((560, 0, width, height))),
            "thumbnail150": image.resize((150, 99), Image.Resampling.LANCZOS),
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
    args = parser.parse_args()
    main(args.source, args.output)
