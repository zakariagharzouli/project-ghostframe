"""Génère des PNG carrés et des contre-exemples appariés pour les essais de profil."""

import argparse
import csv
import io
import json
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageCms, ImageDraw

import ghostframe as gf
from lab import save_json
from pngcheck import describe, must

FORMATS = (320, 400, 512)
REFERENCE = "IG02_apng_rgba_320"
COLORS = ("#18dcb8", "#f6a540", "#ee72ae", "#8098ff")
MANUAL_OBSERVATIONS = Path(__file__).parent / "evidence" / "phase3" / "essais-profils.json"


def demo_motion(size):
    frames = []
    for index, color in enumerate(COLORS):
        image = Image.new("RGBA", (320, 320), "#101a2b")
        pen = ImageDraw.Draw(image)
        pen.rounded_rectangle((24, 24, 296, 296), radius=42, fill="#192a42", outline="#38546c", width=2)
        pen.ellipse((66, 66, 254, 254), outline="#54758c", width=4)
        for j, (x, y) in enumerate(((160, 82), (238, 160), (160, 238), (82, 160))):
            fills = color if index == j else "#334e66"
            pen.ellipse((x - 19, y - 19, x + 19, y + 19), fill=fills)
        pen.rectangle((42, 44, 80, 52), fill=color)
        pen.ellipse((138, 138, 182, 182), fill="#263e56")
        if size != 320:
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        frames.append(image.tobytes())
    return gf.Motion(size, size, tuple(frames), (350,) * len(frames))


def resize_motion(motion, size):
    source = (motion.width, motion.height)
    frames = tuple(Image.frombytes("RGBA", source, data).resize((size, size), Image.Resampling.LANCZOS).tobytes()
                   for data in motion.frames)
    return gf.Motion(size, size, frames, motion.delays, motion.plays)


def transparent_patch(motion):
    frames = []
    for frame in motion.frames:
        image = Image.frombytes("RGBA", (motion.width, motion.height), frame)
        alpha = image.getchannel("A")
        ImageDraw.Draw(alpha).rectangle((2, 2, 14, 14), fill=0)
        image.putalpha(alpha)
        frames.append(image.tobytes())
    return gf.Motion(motion.width, motion.height, tuple(frames), motion.delays, motion.plays)


def icc_chunk():
    profile = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    # LittleCMS stamps generated profiles with the wall clock. An unset profile ID is permitted.
    struct.pack_into(">6H", profile, 24, 2026, 1, 1, 0, 0, 0)
    profile[84:100] = bytes(16)
    ImageCms.getOpenProfile(io.BytesIO(profile))
    return b"Ghostframe sRGB\x00\x00" + zlib.compress(profile, 9)


def add_chunk(blob, kind, value):
    stream = gf.chunks(blob)
    return gf.serialize([stream[0], (kind, value), *stream[1:]])


def raster_bytes(blob):
    return gf.serialize([(kind, data) for kind, data in gf.chunks(blob) if kind in (b"IHDR", b"IDAT", b"IEND")])


def compatibility_cases(motion=None, standard=None, archived=None):
    if motion is None:
        motion = demo_motion(320)
    if standard is None:
        standard = gf.apng(motion)
    if archived is None:
        archived = gf.apng(motion, archive=True)
    sizes = {size: resize_motion(motion, size) if size != 320 else motion for size in FORMATS}
    return {
        "IG01_statique_IDAT_320": ("Trames retirées, IHDR et IDAT conservés", REFERENCE, raster_bytes(standard)),
        REFERENCE: ("APNG témoin, poster inclus, RGBA opaque", None, standard),
        "IG03_apng_rectangles_320": ("Rectangles fcTL avec les mêmes pixels décodés", REFERENCE,
                                      gf.apng(motion, sparse=True)),
        "IG04_apng_poster_separe_320": ("Poster IDAT distinct de la boucle, pixels du poster inchangés", REFERENCE,
                                        gf.apng(motion, poster=motion.frames[0])),
        "IG05_apng_gfRs_320": ("Ajout du bloc privé gfRs", REFERENCE, archived),
        "IG06_apng_rgb_320": ("Couleur type 2, RGB opaque aux mêmes pixels RGBA normalisés", REFERENCE,
                              gf.apng(motion, rgb=True)),
        "IG07_apng_transparent_320": ("Même stockage RGBA, petite zone alpha non opaque", REFERENCE,
                                      gf.apng(transparent_patch(motion))),
        "IG08_apng_sRGB_320": ("Ajout d’une intention sRGB", REFERENCE, add_chunk(standard, b"sRGB", b"\0")),
        "IG09_apng_ICC_320": ("Ajout du profil sRGB explicite iCCP", REFERENCE,
                              add_chunk(standard, b"iCCP", icc_chunk())),
        "IG10_apng_texte_320": ("Ajout d’un bloc texte tEXt", REFERENCE,
                                add_chunk(standard, b"tEXt", b"Description\x00Ghostframe phase 3")),
        "IG11_apng_poids_320": ("Compression zlib niveau 1, pixels et types de blocs conservés", REFERENCE,
                                gf.apng(motion, level=1)),
        "LI01_statique_400": ("Témoin fixe à 400 px", "LI02_apng_400",
                              gf.static_png(400, 400, sizes[400].frames[0])),
        "LI02_apng_400": ("Même séquence à 400 px", REFERENCE, gf.apng(sizes[400])),
        "LI03_statique_512": ("Témoin fixe à 512 px", "LI04_apng_512",
                              gf.static_png(512, 512, sizes[512].frames[0])),
        "LI04_apng_512": ("Même séquence à 512 px", REFERENCE, gf.apng(sizes[512])),
        "N01_apng_rgb_rectangles_320": ("Candidat combiné RGB + rectangles", REFERENCE,
                                        gf.apng(motion, rgb=True, sparse=True)),
    }


def verify_original_pair(original, companion):
    without = [(kind, data) for kind, data in gf.chunks(original) if kind != gf.ARCHIVE]
    return gf.serialize(without) == companion


def write_suite(directory, cases):
    directory.mkdir(parents=True, exist_ok=True)
    records = {key: describe(blob) for key, (_, _, blob) in cases.items()}
    manifests = []
    for key, (factor, reference, blob) in cases.items():
        report = records[key]
        peer = records[reference] if reference else None
        comparison = None if peer is None else {
            "same_poster_pixels": peer["poster_sha256"] == report["poster_sha256"],
            "same_animation": [f["rgba_sha256"] for f in peer["frames"]] == [f["rgba_sha256"] for f in report["frames"]]
            and [f["delay_ms"] for f in peer["frames"]] == [f["delay_ms"] for f in report["frames"]]
            and peer["plays"] == report["plays"],
            "delta_bytes": report["bytes"] - peer["bytes"],
        }
        name = f"{key}.png"
        (directory / name).write_bytes(blob)
        manifests.append({"file": name, "factor": factor, "reference": f"{reference}.png" if reference else None,
                          "comparison": comparison, **report})
    save_json(directory / "manifest.json", manifests)
    return manifests


def observation_columns(result, date):
    delivery = result.get("delivery", {})
    if not result:
        provenance = "généré, non essayé sur la plateforme"
    elif delivery:
        provenance = "observation manuelle utilisateur et mesure CDN publique"
    else:
        provenance = "observation manuelle utilisateur"
    return [provenance, result.get("import", "non testé"), "", delivery.get("sha256"), delivery.get("mime"),
            delivery.get("animation_frames"), result.get("render"), "", result.get("note"), date if result else ""]


def write_manual_matrices(directory, manifests, exact_originals=None):
    observations = json.loads(MANUAL_OBSERVATIONS.read_text(encoding="utf-8"))
    header = ("fichier", "référence", "facteur", "octets", "dimensions", "trames", "sha256_source", "provenance",
              "import", "aperçu_après_import", "sha256_ressource_servie", "mime_ressource",
              "trames_ressource", "rendu_client", "version_client", "message_observé", "date")
    for platform, codes, manual in (
        ("instagram", ("IG", "N0"), [("Residual_Labs_Ghostframe_V1_Instagram.png", "refusé", "", 0)]),
        ("linkedin", ("LI", "N0"), [
            ("A_png_statique_320.png", "accepté", "fixe", 1),
            ("B_apng_standard_320.png", "accepté", "fixe", 2),
            ("C_png_statique_512.png", "accepté", "fixe", 3),
        ]),
    ):
        with (directory / f"matrice-{platform}.csv").open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(header)
            for name, imported, visible, index in manual:
                report = exact_originals[index] if exact_originals else None
                metadata = [report["bytes"], "x".join(map(str, report["dimensions"])),
                            report["animation_frames"], report["sha256"]] if report else ["", "", "", ""]
                writer.writerow([name, "", "", *metadata, "observation manuelle utilisateur", imported,
                                 "", "", "", "", visible, "", "", ""])
            matched = {row["sha256"]: row for row in observations["files"] if platform in row}
            for report in manifests:
                if report["file"].startswith(codes) or (platform == "linkedin" and report["file"].startswith(("IG01", "IG02"))):
                    observed = matched.pop(report["sha256"], None)
                    result = observed[platform] if observed else {}
                    writer.writerow([report["file"], report["reference"], report["factor"], report["bytes"],
                                     "x".join(map(str, report["dimensions"])), report["animation_frames"], report["sha256"],
                                     *observation_columns(result, observations["date"])])
            for observed in matched.values():
                result = observed[platform]
                writer.writerow([observed["file"], "", observed["id"], observed["bytes"],
                                 "x".join(map(str, observed["dimensions"])), observed["frames"], observed["sha256"],
                                 *observation_columns(result, observations["date"])])


def generate(directory, original=None, linkedin_b=None):
    if original or linkedin_b:
        must(original and linkedin_b, "Fournir --instagram et --linkedin-b ensemble")
        instagram, baseline = original.read_bytes(), linkedin_b.read_bytes()
        reports = [describe(instagram), None, describe(baseline), None]
        must(verify_original_pair(instagram, baseline), "Les originaux diffèrent au-delà de gfRs")
        size, default, motion = gf.decoded_png(baseline)
        must(size == (320, 320) and motion is not None and default == motion.frames[0],
             "Séquence 320 × 320 à poster inclus requise")
        cases = compatibility_cases(motion, baseline, instagram)
    else:
        cases = compatibility_cases()
        reports = None
    manifests = write_suite(directory, cases)
    write_manual_matrices(directory, manifests, reports)
    return manifests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("run/phase3-suite"))
    parser.add_argument("--instagram", type=Path)
    parser.add_argument("--linkedin-b", type=Path)
    args = parser.parse_args()
    manifests = generate(args.out, args.instagram, args.linkedin_b)
    print(f"{len(manifests)} PNG validés. {args.out}")


if __name__ == "__main__":
    main()
