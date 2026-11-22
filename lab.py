"""Generate fixtures and audit the bytes and rendering of a local PNG pipeline."""

import argparse
import html
import io
import json
import os
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, __version__ as pillow_version

import ghostframe as gf
from demo import build_capture_preview, build_demo

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 96, 64
COLORS = ("#4dedd1", "#f7be64", "#ff8cb5", "#9aa7ff")
PROFILES = {"copy", "all-frames", "safe-copy", "raster", "resize"}


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def art(index):
    image = Image.new("RGBA", (WIDTH, HEIGHT), "#111d30")
    draw = ImageDraw.Draw(image)
    for x in range(10, WIDTH, 8):
        for y in range(9, HEIGHT, 8):
            draw.point((x, y), fill="#33465d")
    if index is None:
        draw.rectangle((8, 8, 87, 55), outline="#658298")
        draw.text((28, 26), "POSTER", fill="#ffffff")
    else:
        x = 14 + index * 18
        draw.rectangle((x, 20, x + 12, 43), fill=COLORS[index])
        draw.rectangle((10, 52, 85, 53), fill="#324760")
        draw.rectangle((10, 52, 26 + index * 19, 53), fill=COLORS[index])
    return image.tobytes()


def fixture_motion():
    return gf.Motion(WIDTH, HEIGHT, tuple(art(i) for i in range(4)), (350,) * 4)


def fixtures(output):
    motion = fixture_motion()
    alternate = gf.Motion(WIDTH, HEIGHT, (motion.frames[0], *reversed(motion.frames[1:])), motion.delays)
    atlas, manifest = gf.atlas(motion)
    files = {
        "static": gf.static_png(WIDTH, HEIGHT, motion.frames[0]),
        "apng-a": gf.apng(motion),
        "apng-b": gf.apng(alternate),
        "separate-poster": gf.apng(motion, poster=art(None)),
        "ghostframe": gf.apng(motion, archive=True),
        "atlas": atlas,
        **{f"frame-{i}": gf.static_png(WIDTH, HEIGHT, frame) for i, frame in enumerate(motion.frames)},
    }
    inputs = output / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        (inputs / f"{name}.png").write_bytes(blob)
    save_json(inputs / "atlas.json", manifest)
    return files, manifest


def transform(blob, profile):
    size, default, motion = gf.decoded_png(blob)
    if profile == "copy":
        return blob
    image = Image.frombytes("RGBA", size, default)
    target = io.BytesIO()
    if profile == "all-frames" and motion is not None:
        frames = [Image.frombytes("RGBA", size, frame) for frame in motion.frames]
        separate = default != motion.frames[0]
        base = image if separate else frames.pop(0)
        base.save(
            target, "PNG", save_all=True, append_images=frames, default_image=separate,
            duration=motion.delays, loop=motion.plays, disposal=0, blend=0, compress_level=6,
        )
    else:
        if profile == "resize":
            image = image.resize(tuple(max(1, dimension // 2) for dimension in size), Image.Resampling.LANCZOS)
        image.save(target, "PNG", compress_level=6)
    rendered = target.getvalue()
    if profile == "safe-copy":
        retained = [(kind, payload) for kind, payload in gf.chunks(blob) if kind == gf.ARCHIVE]
        stream = gf.chunks(rendered)
        rendered = gf.serialize([*stream[:-1], *retained, stream[-1]])
    return rendered


PAGE_CSS = """
* { box-sizing: border-box }
body { margin: 20px; font: 14px system-ui; background: #e8edf5; color: #172a41 }
h1 { margin: 0 0 16px; font-size: 24px; line-height: 30px }
main { display: grid; grid-template-columns: repeat(4, 260px); gap: 12px }
section { background: white; padding: 10px; min-height: 114px }
h2 { font-size: 13px; line-height: 20px; margin: 0 0 8px }
.probe { display: block; width: 96px; height: 64px }
.atlas-still { object-fit: none; object-position: left top }
.background { background-repeat: no-repeat }
.atlas { background-repeat: no-repeat; animation: cycle 1400ms steps(4, end) infinite }
@keyframes cycle { to { background-position: 0 -256px } }
"""

PAGE_JS = """
window.ready = Promise.all(Array.from(document.querySelectorAll('img'), img => img.decode()));
for (const canvas of document.querySelectorAll('canvas')) {
  const image = new Image();
  image.src = canvas.dataset.src;
  const context = canvas.getContext('2d');
  window.ready = Promise.all([window.ready, image.decode().then(() => {
    const draw = () => {
      context.drawImage(image, 0, 0);
      requestAnimationFrame(draw);
    };
    draw();
  })]);
}
"""


def test_page(probes):
    cards = []
    for probe in probes:
        name, url, surface = (probe[k] for k in ("name", "url", "surface"))
        extra_class = " atlas-still" if probe["case"] == "atlas-raster" and surface == "img" else ""
        common = f'class="probe {surface}{extra_class}" data-probe="{html.escape(name)}"'
        if surface == "canvas":
            element = f'<canvas {common} width="96" height="64" data-src="{url}"></canvas>'
        elif surface == "img":
            element = f'<img {common} src="{url}" alt="" width="96" height="64">'
        else:
            element = f'<div {common} style="background-image:url({url})"></div>'
        cards.append(f"<section><h2>{html.escape(name)}</h2>{element}</section>")
    return (
        '<!doctype html><html lang="fr"><meta charset="utf-8"><title>Ghostframe — banc de mesure</title>'
        f"<style>{PAGE_CSS}</style><h1>Banc de mesure Ghostframe</h1><main>{''.join(cards)}</main>"
        f"<script>{PAGE_JS}</script>"
    ).encode()


@contextmanager
def local_lab():
    storage = {}
    pages = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, content_type, body):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            match = re.fullmatch(r"/images/([0-9a-f]{64})\.png", self.path)
            if self.path in pages:
                self.reply(200, "text/html; charset=utf-8", pages[self.path])
            elif match and match[1] in storage:
                self.reply(200, "image/png", storage[match[1]])
            else:
                self.send_error(404)

        def do_POST(self):
            profile = self.path.removeprefix("/upload/")
            if not self.path.startswith("/upload/") or profile not in PROFILES:
                self.send_error(404)
                return
            if self.headers.get_content_type() != "image/png":
                self.send_error(415)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= gf.MAX_FILE:
                    self.send_error(413)
                    return
                incoming = self.rfile.read(length)
                rendered = transform(incoming, profile)
            except (ValueError, KeyError, OSError, SyntaxError, EOFError, gf.zlib.error, gf.struct.error):
                self.send_error(422)
                return
            key = gf.digest(rendered)
            storage[key] = rendered
            answer = json.dumps({"url": f"/images/{key}.png"}).encode()
            self.reply(201, "application/json", answer)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", pages
        finally:
            server.shutdown()
            thread.join()


def submit(base, blob, profile):
    request = Request(f"{base}/upload/{profile}", data=blob, headers={"Content-Type": "image/png"})
    with urlopen(request, timeout=15) as response:
        status = response.status
        url = json.load(response)["url"]
    with urlopen(f"{base}{url}", timeout=15) as response:
        returned = response.read()
        return returned, {
            "upload_status": status,
            "download_status": response.status,
            "content_type": response.headers["Content-Type"],
            "url": url,
        }


def measure_transports(base, output, inputs, manifest):
    reports = {}
    artifacts = {}
    output.mkdir(exist_ok=True)

    def run(name, profile, source, blob=None, note=None):
        incoming = inputs[source] if blob is None else blob
        returned, http = submit(base, incoming, profile)
        before, after = gf.inspect(incoming), gf.inspect(returned)
        report = {"profile": profile, "source": source, "http": http, "before": before, "after": after}
        report["same_file"] = before["sha256"] == after["sha256"]
        report["same_default"] = before["default_sha256"] == after["default_sha256"]
        report["same_motion"] = None if before["motion"] is None else before["motion"] == after["motion"]
        if note is not None:
            report["recovery"] = note
        reports[name] = report
        artifacts[name] = returned
        (output / f"{name}.png").write_bytes(returned)

    for name, profile, source in (
        ("static-copy", "copy", "static"),
        ("apng-copy", "copy", "apng-a"),
        ("poster-copy", "copy", "separate-poster"),
        ("ghostframe-copy", "copy", "ghostframe"),
        ("apng-all-frames", "all-frames", "apng-a"),
        ("poster-all-frames", "all-frames", "separate-poster"),
        ("apng-raster-a", "raster", "apng-a"),
        ("apng-raster-b", "raster", "apng-b"),
        ("ghostframe-safe-copy", "safe-copy", "ghostframe"),
        ("ghostframe-raster", "raster", "ghostframe"),
        ("ghostframe-resize", "resize", "ghostframe"),
        ("atlas-raster", "raster", "atlas"),
        ("atlas-resize", "resize", "atlas"),
    ):
        run(name, profile, source)

    recovered = gf.recover(artifacts["ghostframe-safe-copy"])
    run("ghostframe-recovered", "copy", "ghostframe-safe-copy", recovered, "gfRs → APNG")
    atlas_motion = gf.from_atlas(artifacts["atlas-raster"], manifest)
    run("atlas-recovered", "copy", "atlas-raster", gf.apng(atlas_motion), "atlas + manifeste → APNG")

    original = gf.inspect(inputs["apng-a"])["motion"]
    for name in ("ghostframe-recovered", "atlas-recovered", "apng-all-frames"):
        assert reports[name]["after"]["motion"] == original, name
    assert reports["poster-all-frames"]["same_motion"] and reports["poster-all-frames"]["same_default"]
    assert gf.inspect(inputs["apng-b"])["motion"] != original
    assert artifacts["apng-raster-a"] == artifacts["apng-raster-b"]
    assert reports["ghostframe-safe-copy"]["after"]["motion"] is None

    rejected = {}
    for name, fn in (
        ("raster-sans-bloc", lambda: gf.recover(artifacts["ghostframe-raster"])),
        ("atlas-redimensionné", lambda: gf.from_atlas(artifacts["atlas-resize"], manifest)),
    ):
        try:
            fn()
        except ValueError as error:
            rejected[name] = str(error)
        else:
            raise AssertionError(f"Une restauration aurait dû échouer pour {name}")
    return reports, artifacts, {
        "distinct_apng_same_flat_bytes": True,
        "flat_sha256": gf.digest(artifacts["apng-raster-a"]),
        "rejected_recovery": rejected,
    }


def probes_for(reports):
    probes = []
    for name, case, surface, moving in (
        ("Témoin statique", "static-copy", "img", False),
        ("APNG servi en image/png", "apng-copy", "img", True),
        ("APNG en arrière-plan CSS", "apng-copy", "background", True),
        ("Même APNG dans canvas", "apng-copy", "canvas", False),
        ("APNG avec poster séparé", "poster-copy", "img", True),
        ("Poster séparé dans canvas", "poster-copy", "canvas", False),
        ("Ghostframe d’origine", "ghostframe-copy", "img", True),
        ("APNG transcodé", "apng-all-frames", "img", True),
        ("APNG aplati", "apng-raster-a", "img", False),
        ("Bloc Ghostframe seul", "ghostframe-safe-copy", "img", False),
        ("Ghostframe restauré", "ghostframe-recovered", "img", True),
        ("Atlas statique, zone haute", "atlas-raster", "img", False),
        ("Même atlas animé en CSS", "atlas-raster", "atlas", True),
        ("Atlas reconstruit en APNG", "atlas-recovered", "img", True),
    ):
        probes.append({
            "name": name, "case": case, "surface": surface, "expected_moving": moving,
            "url": reports[case]["http"]["url"],
        })
    return probes


def visual_audit(base, output, browser, probes, reports, manifest):
    captures = (output / "captures").resolve()
    captures.mkdir(exist_ok=True)
    command = ["node", str(ROOT / "web" / "capture.mjs"), f"{base}/probe", str(captures)]
    if browser:
        command.append(browser)
    subprocess.run(command, check=True, timeout=70)
    record = json.loads((captures / "capture.json").read_text(encoding="utf-8"))
    positions = {item["name"]: item for item in record.pop("positions")}
    histograms = {probe["name"]: {} for probe in probes}
    for sample in record["samples"]:
        with Image.open(captures / sample["file"]) as shot:
            sample["render_sha256"] = {}
            for name, rect in positions.items():
                x, y = rect["x"], rect["y"]
                tile = shot.crop((x, y, x + WIDTH, y + HEIGHT)).convert("RGBA")
                key = gf.digest(tile.tobytes())
                counts = histograms[name]
                counts[key] = counts.get(key, 0) + 1
                sample["render_sha256"][name] = key

    record["probes"] = []
    for probe in probes:
        after = reports[probe["case"]]["after"]
        if probe["surface"] == "atlas":
            expected = manifest["frames"]
        elif not probe["expected_moving"]:
            if probe["case"] == "atlas-raster":
                expected = manifest["frames"][:1]
            else:
                expected = [after["default_sha256"]]
        else:
            expected = after["motion"]["frames"]
        counts = histograms[probe["name"]]
        matches_expected = set(counts) == set(expected)
        evidence = {}
        passed = matches_expected
        if probe["surface"] == "canvas":
            first = after["motion"]["frames"][0]
            evidence["matches_html_default_image"] = matches_expected
            evidence["matches_first_animation_frame"] = set(counts) == {first}
            passed = matches_expected or evidence["matches_first_animation_frame"]
        record["probes"].append({
            **probe, "rect": positions[probe["name"]], "expected_sha256": expected,
            "observed_sha256_counts": counts, "distinct": len(counts), **evidence, "pass": passed,
        })
    return record


def run(output, browser, no_browser):
    output.mkdir(parents=True, exist_ok=True)
    inputs, manifest = fixtures(output)
    with local_lab() as (base, pages):
        cases, artifacts, invariants = measure_transports(base, output / "processed", inputs, manifest)
        probes = probes_for(cases)
        pages["/probe"] = test_page(probes)
        record = {
            "measured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "pillow": pillow_version,
            "inputs": {name: gf.inspect(blob) for name, blob in inputs.items()},
            "transports": cases,
            "invariants": invariants,
        }
        build_demo(output / "demo.html", artifacts)
        if not no_browser:
            record["browser"] = visual_audit(base, output, browser, probes, cases, manifest)
            build_capture_preview(output / "render.gif", output / "captures", record["browser"])
        save_json(output / "report.json", record)
        if not no_browser and not all(item["pass"] for item in record["browser"]["probes"]):
            raise RuntimeError("Échec des mesures de rendu. Consulter report.json.")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "run")
    parser.add_argument("--browser", help="Chemin de Chrome, Chromium ou Edge")
    parser.add_argument("--no-browser", action="store_true", help="Mesure HTTP et décodage uniquement")
    args = parser.parse_args()
    result = run(args.out, args.browser, args.no_browser)
    print(f"{len(result['transports'])} parcours HTTP, {len(result.get('browser', {}).get('probes', []))} surfaces.")


if __name__ == "__main__":
    main()
