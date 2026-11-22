"""Vérifie l'enveloppe PNG, les flux de pixels et la structure APNG."""

import argparse
import io
import json
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageCms

import ghostframe as gf

DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
         (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
CRITICAL = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
ANIMATION = {b"acTL", b"fcTL", b"fdAT"}
PRE_PALETTE = {b"iCCP", b"sRGB", b"gAMA", b"cHRM", b"sBIT", b"cICP"}
OTHER_FORMATS = {"JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif", "AVIF": "image/avif"}


def must(condition, error):
    if not condition:
        raise ValueError(error)


def inflate(parts, maximum):
    decoder = zlib.decompressobj()
    value = decoder.decompress(b"".join(parts), maximum + 1)
    must(len(value) <= maximum and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
         "Flux zlib incomplet, surnuméraire ou trop volumineux")
    return value


def check_scanlines(parts, width, height, bits, interlace):
    passes = ADAM7 if interlace else ((0, 0, 1, 1),)
    spans = []
    for x, y, dx, dy in passes:
        columns = max(0, (width - x + dx - 1) // dx)
        rows = max(0, (height - y + dy - 1) // dy)
        if columns and rows:
            spans.append((rows, 1 + (columns * bits + 7) // 8))
    expected = sum(rows * stride for rows, stride in spans)
    raster = inflate(parts, expected)
    must(len(raster) == expected, "Longueur décompressée des lignes PNG incorrecte")
    offset = 0
    for rows, stride in spans:
        end = offset + rows * stride
        must(all(value <= 4 for value in raster[offset:end:stride]), "Filtre de ligne PNG invalide")
        offset = end


def profile_blocks(stream, kinds, depth, color, first_idat):
    if b"PLTE" in kinds:
        index = kinds.index(b"PLTE")
        palette = stream[index][1]
        must(kinds.count(b"PLTE") == 1 and index < first_idat and color not in (0, 4)
             and 3 <= len(palette) <= 768 and len(palette) % 3 == 0, "PLTE invalide")
    else:
        palette = None
    if color == 3:
        must(palette is not None and len(palette) // 3 <= 2 ** depth, "Palette indexée absente ou trop grande")
    if b"tRNS" in kinds:
        index = kinds.index(b"tRNS")
        length = len(stream[index][1])
        correct_length = ((color == 0 and length == 2) or (color == 2 and length == 6)
                          or (color == 3 and palette and 0 < length <= len(palette) // 3))
        after_palette = palette is None or index > kinds.index(b"PLTE")
        must(kinds.count(b"tRNS") == 1 and index < first_idat and correct_length and after_palette, "tRNS invalide")
    before = min(first_idat, kinds.index(b"PLTE")) if palette else first_idat
    for chunk in PRE_PALETTE.intersection(kinds):
        must(kinds.count(chunk) == 1 and kinds.index(chunk) < before, f"Ordre ou multiplicité de {chunk.decode()}")
    if b"sRGB" in kinds:
        data = stream[kinds.index(b"sRGB")][1]
        must(len(data) == 1 and data[0] <= 3, "Intention sRGB invalide")
    if b"iCCP" in kinds:
        name, sep, compressed = stream[kinds.index(b"iCCP")][1].partition(b"\0")
        must(1 <= len(name) <= 79 and sep and compressed.startswith(b"\0"), "En-tête iCCP invalide")
        profile = inflate([compressed[1:]], 4 * 1024 * 1024)
        must(len(profile) >= 128 and profile[36:40] == b"acsp"
             and int.from_bytes(profile[:4], "big") == len(profile), "Profil ICC invalide")
        ImageCms.getOpenProfile(io.BytesIO(profile))


def animation_details(stream, kinds, canvas, bits, interlace):
    if not ANIMATION.intersection(kinds):
        return None
    first_idat = kinds.index(b"IDAT")
    last_idat = first_idat + kinds.count(b"IDAT") - 1
    must(kinds.count(b"acTL") == 1 and kinds.index(b"acTL") < first_idat, "acTL absent, dupliqué ou tardif")
    control = stream[kinds.index(b"acTL")][1]
    must(len(control) == 8, "Longueur acTL invalide")
    count, plays = struct.unpack(">II", control)
    must(0 < count <= gf.MAX_FRAMES and count == kinds.count(b"fcTL"), "Nombre de trames APNG incohérent")
    must(count * gf.rgba_length(*canvas) <= gf.MAX_MOTION, "Animation au-delà de la limite Ghostframe")
    width, height = canvas
    sequence = 0
    frames = []
    for index, (chunk, data) in enumerate(stream):
        if chunk not in (b"fcTL", b"fdAT"):
            continue
        must(len(data) >= 4 and int.from_bytes(data[:4], "big") == sequence, "Séquence fcTL/fdAT non contiguë")
        sequence += 1
        if chunk == b"fdAT":
            must(frames and not frames[-1]["uses_idat"] and index > last_idat, "fdAT sans fcTL associé après IDAT")
            frames[-1]["parts"].append(data[4:])
            continue
        must(len(data) == 26, "Longueur fcTL invalide")
        _, w, h, x, y, numerator, denominator, disposal, blend = struct.unpack(">IIIIIHHBB", data)
        must(w > 0 and h > 0 and x + w <= width and y + h <= height, "Rectangle APNG hors canevas")
        must(disposal <= 2 and blend <= 1, "Opération APNG invalide")
        uses_idat = index < first_idat
        if uses_idat:
            must(not frames and (w, h, x, y) == (width, height, 0, 0),
                 "La trame IDAT doit couvrir le canevas")
        frames.append({"rect": [x, y, w, h], "delay": [numerator, denominator or 100], "dispose": disposal,
                       "blend": blend, "uses_idat": uses_idat, "parts": []})
    for frame in frames:
        parts = frame.pop("parts")
        if not frame["uses_idat"]:
            must(parts, "Trame APNG sans données fdAT")
            check_scanlines(parts, *frame["rect"][2:], bits, interlace)
    return {"plays": plays, "default_in_animation": frames[0]["uses_idat"], "frames": frames}


def validate_png(blob):
    stream = gf.chunks(blob)
    kinds = [kind for kind, _ in stream]
    must(all(kind[:1].islower() or kind in CRITICAL for kind in kinds), "Bloc critique PNG inconnu")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", stream[0][1])
    must(depth in DEPTHS.get(color, ()) and compression == filtering == 0 and interlace in (0, 1),
         "Propriétés IHDR invalides")
    profile_blocks(stream, kinds, depth, color, kinds.index(b"IDAT"))
    bits = depth * CHANNELS[color]
    check_scanlines([data for kind, data in stream if kind == b"IDAT"], width, height, bits, interlace)
    animation = animation_details(stream, kinds, (width, height), bits, interlace)
    inventory, offset = [], len(gf.SIGNATURE)
    for kind, data in stream:
        inventory.append({"type": kind.decode(), "offset": offset, "bytes": len(data), "sha256": gf.digest(data)})
        offset += 12 + len(data)
    return {
        "width": width, "height": height, "bit_depth": depth, "color_type": color,
        "interlace": interlace, "chunks": inventory, "animation": animation,
        "color_blocks": [kind.decode() for kind in kinds if kind in PRE_PALETTE],
        "metadata_blocks": [kind.decode() for kind in kinds if kind in {b"pHYs", b"tEXt", b"zTXt", b"iTXt", b"eXIf"}],
    }


def describe(blob, source_box=None):
    must(len(blob) <= gf.MAX_FILE, "Fichier au-delà de la limite Ghostframe")
    png = validate_png(blob) if blob.startswith(gf.SIGNATURE) else None
    accepted_formats = ["PNG"] if png else list(OTHER_FORMATS)
    with Image.open(io.BytesIO(blob), formats=accepted_formats) as image:
        size = list(image.size)
        gf.rgba_length(*size)
        name, mode = image.format, image.mode
        alpha = image.convert("RGBA")
        poster_sha = gf.digest(alpha.tobytes())
        count = getattr(image, "n_frames", 1)
        plays = image.info.get("loop", 0)
        start = int(bool(png and png["animation"] and not png["animation"]["default_in_animation"]))
        if png and png["animation"]:
            must(count == len(png["animation"]["frames"]) + start, "Le décodeur ne retrouve pas toutes les trames APNG")
        animated = bool(png and png["animation"]) or count > 1
        must(count <= gf.MAX_FRAMES + start and (count - start) * gf.rgba_length(*size) <= gf.MAX_MOTION,
             "Décodage au-delà de la limite Ghostframe")
        if source_box:
            x, y, w, h = source_box
            must(min(x, y) >= 0 and min(w, h) > 0 and x + w <= size[0] and y + h <= size[1],
                 "Zone source hors image")
            box = (x, y, x + w, y + h)
        else:
            box = None
        selected = alpha.crop(box) if box else alpha
        frame_data = []
        if animated:
            for index in range(start, count):
                image.seek(index)
                frame = image.convert("RGBA")
                if png:
                    numerator, denominator = png["animation"]["frames"][index - start]["delay"]
                    delay = 1000 * numerator / denominator
                else:
                    delay = image.info.get("duration")
                frame_data.append({
                    "rgba_sha256": gf.digest(frame.tobytes()),
                    "region_sha256": gf.digest(frame.crop(box).tobytes()) if box else None,
                    "alpha": list(frame.getchannel("A").getextrema()), "delay_ms": delay,
                })
        return {
            "format": name, "mime_from_bytes": "image/png" if png else OTHER_FORMATS[name],
            "dimensions": size, "bytes": len(blob), "sha256": gf.digest(blob), "mode": mode,
            "poster_sha256": poster_sha, "poster_alpha": list(alpha.getchannel("A").getextrema()),
            "region_poster_sha256": gf.digest(selected.tobytes()),
            "region_size": list(selected.size), "animation_frames": len(frame_data),
            "distinct_animation_frames": len({frame["rgba_sha256"] for frame in frame_data}),
            "plays": plays if animated else None, "frames": frame_data, "png": png,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    reports = []
    for file in args.files:
        try:
            reports.append({"file": file.name, "valid": True, **describe(file.read_bytes())})
        except (ValueError, SyntaxError, EOFError, OSError, zlib.error, ImageCms.PyCMSError) as error:
            reports.append({"file": file.name, "valid": False, "error": str(error)})
    print(json.dumps(reports, indent=2))
    return int(any(not item["valid"] for item in reports))


if __name__ == "__main__":
    raise SystemExit(main())
