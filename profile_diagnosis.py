"""Attribue la perte d'animation à l'import, à la livraison ou au rendu."""

import argparse
import json
import zlib
from collections import Counter
from pathlib import Path

from PIL import ImageCms

from audit_pair import capture_hash
from pngcheck import describe, must

UNKNOWN = "indéterminé"
DELIVERY_LOSS = "animation_absente_de_la_ressource_servie"
RENDER_FIXED = "animation_livrée_rendu_fixe_observé"
NATIVE = "animation_native_observée"


def temporal_identity(report):
    return report["plays"], tuple((frame["rgba_sha256"], frame["delay_ms"]) for frame in report["frames"])


def payload_inventory(before, after):
    old = Counter((c["type"], c["sha256"]) for c in (before["png"] or {}).get("chunks", []))
    new = Counter((c["type"], c["sha256"]) for c in (after["png"] or {}).get("chunks", []))
    summarize = lambda items: dict(sorted(Counter(kind for kind, _ in items.elements()).items()))
    return {"unchanged": summarize(old & new), "old_missing_or_modified": summarize(old - new),
            "new_or_modified": summarize(new - old)}


def time_coverage(times, after):
    if len(times) < 3 or after["plays"] != 0:
        return False
    delays = [frame["delay_ms"] for frame in after["frames"]]
    return bool(delays) and all(delay is not None and delay > 0 for delay in delays) and (
        times[-1] - times[0] >= 2 * sum(delays)
        and max(b - a for a, b in zip(times, times[1:])) < min(delays)
    )


def render_evidence(after, samples, standard_client):
    times = [sample["elapsed_ms"] for sample in samples]
    must(all(isinstance(t, int) and t >= 0 for t in times) and times == sorted(set(times)),
         "Horodatages strictement croissants requis")
    counts = Counter(sample["sha256"] for sample in samples)
    exact_dimensions = bool(samples) and all(sample["size"] == after["region_size"] for sample in samples)
    frame_hashes = {frame["region_sha256"] or frame["rgba_sha256"] for frame in after["frames"]}
    known_hashes = frame_hashes | {after["region_poster_sha256"]}
    matches_animation = counts.keys() & frame_hashes
    coverage = time_coverage(times, after)
    outcome = UNKNOWN
    if standard_client is True and exact_dimensions and counts.keys() <= known_hashes:
        if len(matches_animation) >= 2:
            outcome = "animé"
        elif len(counts) == 1 and (coverage or
                                   (not after["animation_frames"] and len(times) >= 3 and times[-1] - times[0] >= 700)):
            outcome = "fixe"
    return {
        "result": outcome, "capture_count": len(samples), "distinct_regions": len(counts),
        "matches_decoded_animation_regions": len(matches_animation),
        "hash_counts": dict(counts), "compatible_region_dimensions": exact_dimensions,
        "coverage_two_loops": coverage, "all_animation_regions_seen": bool(frame_hashes) and frame_hashes <= counts.keys(),
        "elapsed_ms": times,
    }


def compare(original, delivered, variant, samples, accepted):
    before = describe(original)
    after = describe(delivered, variant.get("source_box"))
    mime = (variant.get("mime") or "").partition(";")[0].strip().lower()
    mime_matches = (mime == after["mime_from_bytes"] or
                    (mime == "image/apng" and after["mime_from_bytes"] == "image/png" and after["animation_frames"] > 0))
    render = render_evidence(after, samples, variant.get("standard_client"))
    stage = UNKNOWN
    verified = variant.get("delivery_verified") is True
    if accepted is False:
        stage = "import_refusé"
    elif accepted is True and verified and mime_matches:
        if before["distinct_animation_frames"] == 0:
            stage = "témoin_statique"
        elif not after["animation_frames"]:
            stage = DELIVERY_LOSS
        elif after["distinct_animation_frames"] < 2:
            stage = "trames_livrées_sans_variation"
        elif render["result"] == "fixe":
            stage = RENDER_FIXED
        elif render["result"] == "animé":
            stage = NATIVE
        else:
            stage = "animation_livrée_rendu_indéterminé"
    return {
        "role": variant.get("role"), "client": variant.get("client"), "import_accepted": accepted,
        "delivery_verified": verified, "response_mime": mime or None, "mime_matches": mime_matches,
        "before": before, "after": after,
        "same_file": before["sha256"] == after["sha256"],
        "same_dimensions": before["dimensions"] == after["dimensions"],
        "same_poster_pixels": before["poster_sha256"] == after["poster_sha256"],
        "same_animation_pixels_and_timing": bool(before["animation_frames"]) and
        temporal_identity(before) == temporal_identity(after),
        "blocks": payload_inventory(before, after), "render": render, "diagnosis": stage,
    }


def audit(original, receipt, directory):
    rows = []
    for variant in receipt.get("variants", []):
        if not variant.get("file"):
            rows.append({"role": variant.get("role"), "diagnosis": UNKNOWN,
                         "manual_render": variant.get("manual_render"), "reason": "Octets servis absents"})
            continue
        samples = []
        for sample in variant.get("captures", []):
            size, fingerprint = capture_hash(directory / sample["file"], variant.get("capture_box"))
            samples.append({"elapsed_ms": sample["elapsed_ms"], "size": size, "sha256": fingerprint})
        rows.append(compare(original, (directory / variant["file"]).read_bytes(), variant, samples, receipt.get("accepted")))
    return {"platform": receipt.get("platform"), "requested_surface": receipt.get("surface"),
            "import_accepted": receipt.get("accepted"), "manual_render": receipt.get("manual_render"),
            "variants": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
        print(json.dumps(audit(args.original.read_bytes(), receipt, args.receipt.parent), indent=2))
    except (ValueError, KeyError, TypeError, OSError, SyntaxError, EOFError, zlib.error, ImageCms.PyCMSError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
