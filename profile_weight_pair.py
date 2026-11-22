"""Génère des PNG et APNG à 0, 1 et 2 trames de même poids."""

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
SINGLE = "IG14_apng_1_trame_poids_egal_320"
REGION = "IG15_apng_2_trames_rectangle_320"
FULL = "IG16_apng_2_trames_pleines_320"
PATCH_X, PATCH_Y, PATCH_SIZE = 62, 33, 32


def frame_control(index, width, height, x, y, *, blend=0):
    return b"fcTL", struct.pack(">IIIIIHHBB", index, width, height, x, y, 500, 1000, 0, blend)


def pad_with_text(blob, target_bytes, note):
    length = target_bytes - len(blob) - 12
    must(len(note) <= length, "Espace insuffisant pour égaliser le poids")
    padded = add_chunk(blob, b"tEXt", note.ljust(length))
    must(len(padded) == target_bytes, "Les témoins doivent avoir la même taille")
    return padded


def opaque_square(blob):
    source = describe(blob)
    must(source["png"] and source["png"]["bit_depth"] == 8 and source["png"]["color_type"] in (2, 6)
         and source["png"]["interlace"] == 0 and source["dimensions"] == [320, 320]
         and source["animation_frames"] == 0 and source["poster_alpha"] == [255, 255],
         "Un PNG RGB ou RGBA opaque non entrelacé de 320 × 320 est requis")
    return source


def draw_marker(region):
    ImageDraw.Draw(region).ellipse((2, 2, 29, 29), fill="#ffffff", outline="#ffae35", width=4)


def two_frame_png(critical, image, x, y, *, rgb=False, blend=0):
    width, height = image.size
    data = gf.compressed_pixels(width, height, image.tobytes(), rgb=rgb)
    return gf.serialize([
        critical[0], (b"acTL", struct.pack(">II", 2, 0)), frame_control(0, 320, 320, 0, 0),
        *critical[1:-1], frame_control(1, width, height, x, y, blend=blend),
        (b"fdAT", struct.pack(">I", 2) + data), critical[-1],
    ])


def pair(blob):
    source = opaque_square(blob)
    critical = gf.chunks(raster_bytes(blob))
    with Image.open(io.BytesIO(blob), formats=["PNG"]) as image:
        region = image.convert("RGBA").crop((PATCH_X, PATCH_Y, PATCH_X + PATCH_SIZE, PATCH_Y + PATCH_SIZE))
    draw_marker(region)
    animated = two_frame_png(critical, region, PATCH_X, PATCH_Y, rgb=source["png"]["color_type"] == 2)
    baseline = gf.serialize(critical)
    note = b"Description\x00Temoin PNG statique, taille de fichier egale au temoin APNG."
    static = pad_with_text(baseline, len(animated), note)
    return {
        STATIC: ("PNG fixe au poids égal, IDAT conservé, ajout tEXt", ANIMATED, static),
        ANIMATED: ("APNG à deux trames, même poids et même IDAT du poster", None, animated),
    }


def controls(blob):
    results = pair(blob)
    critical = gf.chunks(raster_bytes(blob))
    single = gf.serialize([
        critical[0], (b"acTL", struct.pack(">II", 1, 0)), frame_control(0, 320, 320, 0, 0), *critical[1:],
    ])
    padded = pad_with_text(single, len(results[ANIMATED][2]),
                           b"Description\x00Temoin APNG a une trame, longueur identique.")
    results[SINGLE] = ("APNG sans variation à une trame, sans fdAT, poids et poster identiques", STATIC, padded)
    return results


def frame_bounds_controls(blob):
    source = opaque_square(blob)
    must(source["png"]["color_type"] == 6, "Un PNG RGBA est requis pour la composition OVER")
    critical = gf.chunks(raster_bytes(blob))
    region = Image.new("RGBA", (PATCH_SIZE, PATCH_SIZE))
    draw_marker(region)
    full = Image.new("RGBA", (320, 320))
    full.paste(region, (PATCH_X, PATCH_Y))
    cropped = two_frame_png(critical, region, PATCH_X, PATCH_Y, blend=1)
    complete = two_frame_png(critical, full, 0, 0, blend=1)
    note = b"Description\x00Temoin deux trames, meme taille de fichier."
    size = max(len(cropped), len(complete)) + 12 + len(note)
    return {
        REGION: ("Seconde trame en rectangle 32 × 32, composition OVER", FULL,
                 pad_with_text(cropped, size, note)),
        FULL: ("Seconde trame plein cadre 320 × 320, composition OVER", None,
               pad_with_text(complete, size, note)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=Path("run/phase3-weight-pair"))
    parser.add_argument("--frame-bounds", action="store_true", help="Compare un rectangle à une trame plein cadre")
    args = parser.parse_args()
    generate = frame_bounds_controls if args.frame_bounds else controls
    write_suite(args.out, generate(args.source.read_bytes()))


if __name__ == "__main__":
    main()
