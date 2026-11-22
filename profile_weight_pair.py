"""Génère un PNG statique et un APNG à deux trames de même poids."""

import argparse
import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw

import ghostframe as gf
from pngcheck import describe, must
from profile_fixtures import add_chunk, raster_bytes, write_suite

STATIC = "IG12_png_statique_poids_egal_320"
ANIMATED = "IG13_apng_2_trames_poids_egal_320"


def pair(blob):
    source = describe(blob)
    must(source["png"] and source["png"]["bit_depth"] == 8 and source["png"]["color_type"] in (2, 6)
         and source["png"]["interlace"] == 0 and source["dimensions"] == [320, 320]
         and source["animation_frames"] == 0 and source["poster_alpha"] == [255, 255],
         "Un PNG RGB ou RGBA opaque non entrelacé de 320 × 320 est requis")
    critical = gf.chunks(raster_bytes(blob))
    with Image.open(io.BytesIO(blob), formats=["PNG"]) as image:
        region = image.convert("RGBA").crop((62, 33, 94, 65))
    draw = ImageDraw.Draw(region)
    draw.ellipse((2, 2, 29, 29), fill="#ffffff", outline="#ffae35", width=4)

    def control(index, width, height, x, y):
        return b"fcTL", struct.pack(">IIIIIHHBB", index, width, height, x, y, 500, 1000, 0, 0)

    delta = gf.compressed_pixels(32, 32, region.tobytes(), rgb=source["png"]["color_type"] == 2)
    animated = gf.serialize([
        critical[0], (b"acTL", struct.pack(">II", 2, 0)), control(0, 320, 320, 0, 0),
        *critical[1:-1], control(1, 32, 32, 62, 33), (b"fdAT", struct.pack(">I", 2) + delta), critical[-1],
    ])
    baseline = gf.serialize(critical)
    text_size = len(animated) - len(baseline) - 12
    note = b"Description\x00Temoin PNG statique, taille de fichier egale au temoin APNG."
    static = add_chunk(baseline, b"tEXt", note.ljust(text_size))
    must(len(static) == len(animated), "Les témoins doivent avoir la même taille")
    return {
        STATIC: ("PNG fixe au poids égal, IDAT conservé, ajout tEXt", ANIMATED, static),
        ANIMATED: ("APNG à deux trames, même poids et même IDAT du poster", None, animated),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=Path("run/phase3-weight-pair"))
    args = parser.parse_args()
    write_suite(args.out, pair(args.source.read_bytes()))


if __name__ == "__main__":
    main()
