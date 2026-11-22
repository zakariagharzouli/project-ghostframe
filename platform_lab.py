"""Reproduce the phase 2 HTTP, codec, recovery, and browser matrix."""

import argparse
import base64
import html
import io
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from PIL import Image, ImageDraw, __version__ as pillow_version

import capsule
import ghostframe as gf
from lab import art, capture_tiles, fixture_motion, local_lab, save_json, submit, test_page
from pipelines import FORMATS, TRANSFORMS, changes, describe, versions

ROOT = Path(__file__).resolve().parent
PNG = "image/png"
GITHUB_SAMPLE = (
    "https://raw.githubusercontent.com/zakariagharzouli/project-ghostframe/"
    "f803f9373f87be92d74a2bb557f05d8e5528a542/evidence/inputs/apng-a.png"
)
GITHUB_SAMPLE_SHA = "feed1d04c742edac6796c6119589d1f0a7fc02309c6c3e9a3d1295117ddf29d7"
SUCCESS, FAILURE, UNKNOWN = "succès", "échec", "indéterminé"

CASES = (
    ("reference", "apng", "copy"),
    ("sparse-copy", "sparse", "copy"),
    ("dual-pillow-raster", "dual", "raster"),
    ("dual-pillow-animation", "dual", "all-frames"),
    ("dual-opencv-raster", "dual", "cv-raster"),
    ("dual-opencv-animation", "dual", "cv-animation"),
    ("poster-opencv-animation", "poster", "cv-animation"),
    ("sparse-opencv-animation", "sparse", "cv-animation"),
    ("sparse-opencv-resize", "sparse", "cv-resize"),
    ("sparse-opencv-crop", "sparse", "cv-crop-one"),
    ("sparse-webp", "sparse", "pillow-webp"),
    ("capsule-png", "capsule", "cv-raster"),
    ("capsule-resize", "capsule", "cv-resize"),
    ("capsule-crop", "capsule", "cv-crop-one"),
    ("capsule-jpeg", "capsule", "cv-jpeg"),
    ("capsule-combined", "capsule", "cv-combined"),
    ("capsule-half", "capsule", "cv-crop-half"),
    ("capsule-tiny", "capsule", "cv-tiny"),
    ("capsule-gray", "capsule", "cv-gray"),
)
EXPECTED_NATIVE = {
    "reference", "sparse-copy", "dual-pillow-animation", "dual-opencv-animation",
    "poster-opencv-animation", "sparse-opencv-animation", "sparse-webp", "capsule-reconstructed",
}
EXPECTED_RECOVERY = {"capsule-png", "capsule-resize", "capsule-crop", "capsule-jpeg", "capsule-combined"}


def sparse_corpus():
    width, height = 384, 216
    rng = random.Random(20261122)
    background = Image.frombytes("RGB", (width, height), rng.randbytes(width * height * 3)).convert("RGBA")
    frames = []
    for index in range(6):
        image = background.copy()
        x = 70 + 8 * index
        ImageDraw.Draw(image).rectangle((x, 82, x + 17, 100), fill="#ffcc44")
        frames.append(image.tobytes())
    return gf.Motion(width, height, tuple(frames), (130, 170, 190, 210, 230, 270), 3)


def size_trial(source):
    plain, sparse = gf.apng(source), gf.apng(source, sparse=True)
    assert gf.decoded_png(sparse)[2] == source and gf.decoded_png(plain)[2] == source
    return {
        "size": [source.width, source.height], "frames": len(source.frames),
        "full_bytes": len(plain), "sparse_bytes": len(sparse),
        "reduction_percent": round(100 * (1 - len(sparse) / len(plain)), 2),
        "full_sha256": gf.digest(plain), "sparse_sha256": gf.digest(sparse),
    }


def recovery(blob, expected):
    try:
        result = capsule.decode(blob)
    except (ValueError, SyntaxError, EOFError, OSError, gf.zlib.error) as error:
        return {"result": FAILURE, "reason": str(error)}
    return {
        "result": SUCCESS if result.motion.fingerprint() == expected else FAILURE,
        "shards": list(result.valid_shards), "required": result.required_shards,
        "repaired_index": result.repaired_index, "motion": result.motion.fingerprint(),
    }


def analyze(name, source, profile, incoming, returned, http, directory):
    before, before_pixels = describe(incoming)
    after, after_pixels = describe(returned)
    suffix, expected_type = FORMATS[after["format"]]
    if http["content_type"] != expected_type:
        raise ValueError(f"{name}: MIME de la réponse incohérent avec le décodage")
    artifact = f"{name}.{suffix}"
    (directory / artifact).write_bytes(returned)
    return {
        "name": name, "source": source, "profile": profile, "file": artifact, "http": http,
        "before": before, "after": after, "transform": changes(before, after, before_pixels, after_pixels),
        "native_result": UNKNOWN, "capsule_recovery": None,
    }


def mime_probes(base, input_data):
    negative = (
        ("PNG déclaré en JPEG", "image/jpeg", input_data),
        ("Octets arbitraires déclarés en PNG", PNG, b"not a PNG"),
        ("JPEG véritable déclaré en PNG", PNG, TRANSFORMS["cv-jpeg"](input_data)[0]),
    )
    outcomes = []
    for name, declared, body in negative:
        try:
            _, http = submit(base, body, "copy", declared)
            status = http["upload_status"]
        except HTTPError as error:
            status = error.code
        outcomes.append({"name": name, "declared": declared, "upload_status": status})
    return outcomes


def github_reference(blob, directory):
    with urlopen(GITHUB_SAMPLE, timeout=15) as response:
        returned = response.read(gf.MAX_FILE + 1)
        http = {"upload_status": None, "download_status": response.status,
                "content_type": response.headers.get_content_type(), "url": GITHUB_SAMPLE}
    if gf.digest(returned) != GITHUB_SAMPLE_SHA or gf.inspect(returned)["motion"] != gf.inspect(blob)["motion"]:
        raise ValueError("Le témoin GitHub ne correspond plus à la référence")
    row = analyze("github-raw", "apng", "git-blob + raw CDN", blob, returned, http, directory)
    row["scope"] = "Dépôt GitHub public, ressource brute"
    return row


def browser_trials(base, pages, directory, browser, rows, expected_motion):
    records = []
    for start in range(0, len(rows), 12):
        group = rows[start:start + 12]
        probes = [
            {"name": row["name"], "url": row["http"]["url"], "case": row["name"],
             "surface": "img", "native_size": True}
            for row in group
        ]
        pages["/probe"] = test_page(probes)
        target = directory / f"panel-{len(records) + 1}"
        target.mkdir(exist_ok=True)
        record, positions, histograms = capture_tiles(base, target, browser)
        record["panel"] = target.name
        records.append(record)
        for row in group:
            name, after = row["name"], row["after"]
            hashes = histograms[name]
            motion = after["motion"]
            expected_hashes = set(motion["frames"]) if motion else set()
            exact = set(hashes) == expected_hashes
            row["render"] = {
                "hashes": hashes, "distinct": len(hashes), "panel": target.name,
                "rect": positions[name], "all_decoded_frames_seen": exact if motion else None,
                "scaling": "1:1, top-left sample",
            }
            if len(hashes) >= 2 and exact and motion == expected_motion:
                row["native_result"] = SUCCESS
            elif len(hashes) == 1 and motion is None:
                row["native_result"] = FAILURE
            else:
                row["native_result"] = UNKNOWN
    return records


def matrix(rows, mime, reference_status):
    lines = [
        "# Matrice Phase 2", "",
        "| Cas | HTTP envoi / lecture | MIME sortie | Octets | Image par défaut | Dimensions | Trames décodées | États rendus | Natif | Récupération |",
        "| --- | --- | --- | ---: | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        after, change, http = row["after"], row["transform"], row["http"]
        pixels = "identique" if change["same_default_pixels"] else "modifiée"
        size = " × ".join(map(str, after["size"]))
        rendered = row.get("render", {}).get("distinct", "—")
        upload = http["upload_status"] or "—"
        decode = len(after["motion"]["frames"]) if after["motion"] else 0
        recovery_state = row["capsule_recovery"]["result"] if row["capsule_recovery"] else "—"
        lines.append(f"| {row['name']} | {upload} / {http['download_status']} | {http['content_type']} | "
                     f"{after['bytes']} | {pixels} | {size} | {decode} | {rendered} | "
                     f"{row['native_result']} | {recovery_state} |")
    lines.extend(["", "## Contrôles d’entrée MIME", ""])
    lines.extend(f"- {item['name']} — HTTP {item['upload_status']}" for item in mime)
    lines.extend(["", "## Référence GitHub brute", "", reference_status, ""])
    return "\n".join(lines)


def comparison_demo(rows, output):
    titles = {
        "sparse-copy": "APNG natif à rectangles",
        "sparse-opencv-resize": "Même APNG après redimensionnement OpenCV",
        "sparse-webp": "Sortie WebP animée après transcodage",
        "capsule-combined": "Capsule visible recadrée, réduite et comprimée",
        "capsule-reconstructed": "Animation reconstruite hors de la visionneuse",
    }
    tiles = []
    for name, label in titles.items():
        if name not in rows:
            continue
        row = rows[name]
        mime = row["http"]["content_type"]
        data = base64.b64encode((output / "processed" / row["file"]).read_bytes()).decode()
        label = html.escape(label)
        tiles.append(f'<section><h2>{label}</h2><img alt="{label}" src="data:{mime};base64,{data}"></section>')
    (output / "demo-phase2.html").write_text(
        '<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Ghostframe — Phase 2</title><style>body{background:#121c2c;color:#edf6ff;font:16px system-ui;'
        'padding:20px;max-width:980px;margin:auto}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));'
        'gap:14px}section{padding:16px;background:#1f3048}h2{font-size:17px}img{width:192px;max-width:100%;'
        'height:auto;image-rendering:pixelated}section:nth-child(4) img{width:100%;image-rendering:auto}</style>'
        '<h1>Ghostframe — Phase 2</h1><p>Les images intégrées proviennent des réponses du banc. La capsule JPEG '
        'reste fixe. La dernière image est l’APNG reconstruit en amont à partir de cette capsule.</p><main>'
        + "".join(tiles) + "</main></html>", encoding="utf-8", newline="\n",
    )


def run(output, browser=None, no_browser=False, github_raw=False):
    inputs_dir, processed = output / "inputs", output / "processed"
    for directory in (inputs_dir, processed):
        directory.mkdir(parents=True, exist_ok=True)
    motion = fixture_motion()
    expected_motion = motion.fingerprint()
    inputs = {
        "apng": gf.apng(motion), "dual": gf.apng(motion, archive=True),
        "sparse": gf.apng(motion, sparse=True), "poster": gf.apng(motion, poster=art(None)),
        "capsule": capsule.encode(motion),
    }
    for name, blob in inputs.items():
        (inputs_dir / f"{name}.png").write_bytes(blob)
    rows = []
    reference_status = "Mesure GitHub non demandée. Résultat indéterminé."
    with local_lab(TRANSFORMS) as (base, pages):
        mime = mime_probes(base, inputs["apng"])
        for name, source, profile in CASES:
            returned, http = submit(base, inputs[source], profile)
            row = analyze(name, source, profile, inputs[source], returned, http, processed)
            if source == "capsule":
                row["capsule_recovery"] = recovery(returned, expected_motion)
            rows.append(row)
        combined = next(row for row in rows if row["name"] == "capsule-combined")
        if combined["capsule_recovery"]["result"] == SUCCESS:
            restored = gf.apng(capsule.decode((processed / combined["file"]).read_bytes()).motion, sparse=True)
            returned, http = submit(base, restored, "copy")
            reconstructed = analyze("capsule-reconstructed", "capsule-combined → APNG",
                                    "copy", restored, returned, http, processed)
            reconstructed["scope"] = "Restaurateur Ghostframe exécuté avant la livraison au navigateur"
            rows.append(reconstructed)
        rendered_rows = list(rows)
        if github_raw:
            try:
                row = github_reference(inputs["apng"], processed)
            except (OSError, ValueError, URLError) as error:
                reference_status = f"Lecture GitHub indéterminée. {error}"
            else:
                rows.append(row)
                reference_status = "Le CDN GitHub répond 200 image/png et conserve le fichier octet pour octet."
                if not no_browser and os.environ.get("GHOSTFRAME_TEST_NO_SANDBOX") != "1":
                    rendered_rows.append(row)
                else:
                    reference_status += " Rendu distant non mesuré."
        records = [] if no_browser else browser_trials(base, pages, output, browser, rendered_rows, expected_motion)

    by_name = {row["name"]: row for row in rows}
    report = {
        "measured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "versions": {"python": sys.version.split()[0], "pillow": pillow_version, **versions()},
        "sizes": {"track": size_trial(motion), "fixed_background": size_trial(sparse_corpus())},
        "mime": mime, "github_raw": reference_status, "rows": rows, "browser": records,
    }
    save_json(output / "report.json", report)
    (output / "matrice.md").write_text(matrix(rows, mime, reference_status), encoding="utf-8", newline="\n")
    comparison_demo(by_name, output)
    if records:
        reference = by_name["reference"]
        rect = reference["render"]["rect"]
        record = records[0]
        save_json(output / "receipt-reference.json", {
            "surface": "Chromium, élément img du banc local",
            "accepted_as_png": True, "delivery_mime": PNG, "standard_client": True,
            "box": [rect[key] for key in ("x", "y", "width", "height")],
            "captures": [
                {"elapsed_ms": entry["elapsed_ms"], "file": f"{record['panel']}/captures/{entry['file']}"}
                for entry in record["samples"]
            ],
        })
    return report


def verify(report):
    observed_native = {row["name"]: row["native_result"] for row in report["rows"] if row["name"] != "github-raw"}
    expected_native = {name: SUCCESS if name in EXPECTED_NATIVE else FAILURE
                       for name in {name for name, _, _ in CASES} | {"capsule-reconstructed"}}
    differing = sorted(name for name, status in expected_native.items() if observed_native.get(name) != status)
    observed_recovery = {row["name"] for row in report["rows"]
                         if (row["capsule_recovery"] or {}).get("result") == SUCCESS}
    if observed_recovery != EXPECTED_RECOVERY:
        differing.extend(sorted(observed_recovery ^ EXPECTED_RECOVERY))
    if [probe["upload_status"] for probe in report["mime"]] != [415, 422, 422]:
        differing.append("MIME")
    if differing:
        raise RuntimeError(f"Résultats divergents pour {', '.join(differing)}. Consulter report.json.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "run" / "phase2")
    parser.add_argument("--browser", help="Chemin de Chrome, Chromium ou Edge")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--github-raw", action="store_true", help="Ajoute le témoin public, épinglé par commit")
    parser.add_argument("--verify", action="store_true", help="Vérifie les témoins locaux en incluant le rendu")
    args = parser.parse_args()
    if args.no_browser and args.verify:
        parser.error("--verify exige le rendu navigateur")
    report = run(args.out, args.browser, args.no_browser, args.github_raw)
    if args.verify:
        verify(report)
    counts = {status: sum(row["native_result"] == status for row in report["rows"])
              for status in (SUCCESS, FAILURE, UNKNOWN)}
    print(f"{len(report['rows'])} parcours, {len(report['mime'])} contrôles d’entrée, {counts}")


if __name__ == "__main__":
    main()
