"""Reproduce separate transport and rendering outcomes on profile-sized PNGs."""

import argparse
from datetime import datetime
from pathlib import Path

from PIL import __version__ as pillow_version

import ghostframe as gf
from lab import capture_tiles, local_lab, save_json, submit, test_page
from pipelines import TRANSFORMS, versions
from pngcheck import describe, must
from profile_diagnosis import DELIVERY_LOSS, NATIVE, RENDER_FIXED, audit
from profile_fixtures import REFERENCE, compatibility_cases, raster_bytes, verify_original_pair
from profile_weight_pair import ANIMATED, STATIC, pair

SIZE = [96, 64]
LOCAL_CASES = (
    ("profil-img", REFERENCE, "copy", "img"),
    ("miniature-aplatie", REFERENCE, "raster", "img"),
    ("profil-canvas", REFERENCE, "copy", "canvas"),
    ("profil-opencv-multiframe", REFERENCE, "cv-animation", "img"),
    ("profil-webp-multiframe", REFERENCE, "pillow-webp", "img"),
    ("profil-rgb-rectangles", "N01_apng_rgb_rectangles_320", "copy", "img"),
    ("poids-egal-png", STATIC, "copy", "img"),
    ("poids-egal-apng", ANIMATED, "copy", "img"),
)
EXPECTED = {
    "profil-img": NATIVE, "miniature-aplatie": DELIVERY_LOSS, "profil-canvas": RENDER_FIXED,
    "profil-opencv-multiframe": NATIVE, "profil-webp-multiframe": NATIVE, "profil-rgb-rectangles": NATIVE,
    "poids-egal-png": "témoin_statique", "poids-egal-apng": NATIVE,
    "original-instagram-dans-img": NATIVE, "original-B-dans-img": NATIVE, "original-N01-dans-img": NATIVE,
}


def original_reports(paths):
    instagram, static320, animated, static512 = (p.read_bytes() for p in paths)
    reports = dict(zip(("instagram_v1", "linkedin_a", "linkedin_b", "linkedin_c"),
                       map(describe, (instagram, static320, animated, static512)), strict=True))
    archive = [payload for kind, payload in gf.chunks(instagram) if kind == gf.ARCHIVE]
    archive_motion = gf.read_archive(archive[0])[0] if len(archive) == 1 else None
    _, _, motion = gf.decoded_png(animated)
    relation = {
        "instagram_without_gfRs_is_linkedin_b_byte_for_byte": verify_original_pair(instagram, animated),
        "instagram_gfRs_payload_bytes": len(archive[0]) if len(archive) == 1 else None,
        "archive_frames_equal_linkedin_b": archive_motion is not None and archive_motion == motion,
        "a_and_b_same_poster_rgba": reports["linkedin_a"]["poster_sha256"] == reports["linkedin_b"]["poster_sha256"],
        "a_and_b_same_idat": [block["sha256"] for block in reports["linkedin_a"]["png"]["chunks"]
                            if block["type"] == "IDAT"] ==
                            [block["sha256"] for block in reports["linkedin_b"]["png"]["chunks"] if block["type"] == "IDAT"],
    }
    return {"files": reports, "relationships": relation}, instagram, animated


def run(output, browser, originals):
    output.mkdir(parents=True, exist_ok=True)
    inputs = {key: blob for key, (_, _, blob) in compatibility_cases().items()}
    witnesses = list(LOCAL_CASES)
    scope = "Banc HTTP local. Aucun import effectué sur Instagram ou LinkedIn par ce script."
    report = {"scope": scope, "time": datetime.now().astimezone().isoformat(timespec="seconds"),
              "software": {"pillow": pillow_version, **versions()}}
    if originals:
        report["originals"], inputs["original-instagram"], inputs["original-B"] = original_reports(originals)
        _, _, original_motion = gf.decoded_png(inputs["original-B"])
        must(original_motion is not None, "B doit être animé")
        inputs["original-N01"] = gf.apng(original_motion, rgb=True, sparse=True)
        witnesses.extend((
            ("original-instagram-dans-img", "original-instagram", "copy", "img"),
            ("original-B-dans-img", "original-B", "copy", "img"),
            ("original-N01-dans-img", "original-N01", "copy", "img"),
        ))
    paired_source = raster_bytes(inputs["original-B"]) if originals else inputs["IG01_statique_IDAT_320"]
    inputs.update({key: data for key, (_, _, data) in pair(paired_source).items()})

    probes, deliveries = [], {}
    with local_lab(TRANSFORMS) as (base, pages):
        for name, source, transformation, surface in witnesses:
            data, http = submit(base, inputs[source], transformation)
            must(http["upload_status"] == 201 and http["download_status"] == 200, "Parcours HTTP incomplet")
            suffix = http["url"].rsplit(".", 1)[-1]
            offset = (100, 54) if source.startswith("original-") else (0, 0)
            probes.append({"name": name, "case": name, "surface": surface, "native_size": True,
                           "url": http["url"], "source_offset": offset})
            relative = f"{name}.{suffix}"
            (output / relative).write_bytes(data)
            deliveries[name] = (source, transformation, http, relative, [*offset, *SIZE])
        pages["/probe"] = test_page(probes)
        record, positions, _ = capture_tiles(base, output, browser)

    report["browser"] = record
    for source in dict.fromkeys(source for _, source, _, _ in witnesses):
        (output / f"source-{source}.png").write_bytes(inputs[source])
    receipts, report["comparisons"] = {}, {}
    for name, (source, transformation, http, relative, box) in deliveries.items():
        receipt = receipts.setdefault(source, {"platform": "Ghostframe local", "surface": "Profil carré de laboratoire",
                                               "accepted": True, "variants": []})
        position = positions[name]
        receipt["variants"].append({
            "role": name, "client": record["browser"], "file": relative, "mime": http["content_type"],
            "delivery_verified": True, "standard_client": True,
            "capture_box": [position[key] for key in ("x", "y", "width", "height")], "source_box": box,
            "captures": [{"file": f"captures/{sample['file']}", "elapsed_ms": sample["elapsed_ms"]}
                         for sample in record["samples"]],
            "pipeline": transformation,
        })
    for source, receipt in receipts.items():
        save_json(output / f"recu-{source}.json", receipt)
        comparison = audit(inputs[source], receipt, output)
        for variant in comparison["variants"]:
            name = variant["role"]
            report["comparisons"][name] = {
                **variant, "pipeline": deliveries[name][1], "http": deliveries[name][2],
            }
    save_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("run/phase3-profiles"))
    parser.add_argument("--browser")
    parser.add_argument("--originals", type=Path, nargs=4, metavar=("INSTAGRAM", "A", "B", "C"))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    report = run(args.out, args.browser, args.originals)
    problems = []
    for name, row in report["comparisons"].items():
        print(f"{name}: {row['diagnosis']} ({row['render']['distinct_regions']} régions distinctes)")
        if row["diagnosis"] != EXPECTED[name]:
            problems.append(name)
    if args.verify and problems:
        raise SystemExit(f"Écarts au protocole pour {', '.join(problems)}. Consulter report.json.")


if __name__ == "__main__":
    main()
