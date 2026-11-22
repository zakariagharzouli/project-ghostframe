"""Build a self-contained HTML before/after comparison."""

import base64
from html import escape

from PIL import Image, ImageDraw, ImageFont


CSS = """
:root { color-scheme: dark; font-family: system-ui, sans-serif; background: #111a29; color: #eaf3fb }
* { box-sizing: border-box }
body { max-width: 1030px; margin: auto; padding: 48px 24px }
header { border-bottom: 1px solid #394a60; padding-bottom: 27px; margin-bottom: 24px }
h1 { margin: 0 0 16px; max-width: 22ch; font-size: clamp(32px, 6vw, 58px); line-height: 1.03; letter-spacing: -.05em }
header p { max-width: 60ch; color: #b6c8d8 }
.brand { color: #4dedd1; font: 14px ui-monospace, monospace; margin: 0 0 24px }
main { display: grid; grid-template-columns: repeat(auto-fit, minmax(255px, 1fr)); gap: 14px }
section { background: #1b2940; border: 1px solid #364a64; padding: 18px }
h2 { font-size: 19px; line-height: 1.2; margin: 0 0 13px }
p { line-height: 1.55 }
section p { margin: 12px 0 0; color: #bccddd; font-size: 14px }
.tile { width: 192px; height: 128px; display: block; image-rendering: pixelated; background-color: #111d30 }
.sheet { background-repeat: no-repeat; background-size: 192px 512px; animation: cycle 1400ms steps(4, end) infinite }
@keyframes cycle { to { background-position: 0 -512px } }
@media (prefers-reduced-motion: reduce) { .sheet { animation: none } }
"""


def build_demo(path, artifacts):
    def uri(case):
        return "data:image/png;base64," + base64.b64encode(artifacts[case]).decode("ascii")

    tiles = []
    for label, case, note, sheet in (
        ("APNG d’origine", "apng-copy", "Le navigateur affiche les quatre trames.", False),
        ("APNG après aplatissement", "apng-raster-a", "La sortie ne contient que le raster par défaut.", False),
        ("Bloc Ghostframe conservé", "ghostframe-safe-copy", "Le PNG reste statique. Les trames sont récupérables dans gfRs.", False),
        ("APNG après restauration", "ghostframe-recovered", "Le serveur a reconstruit un APNG à partir de gfRs.", False),
        ("Atlas après réencodage", "atlas-raster", "Le PNG statique contient quatre trames empilées.", False),
        ("Même atlas lu en CSS", "atlas-raster", "La page déplace la fenêtre de lecture sur le même PNG.", True),
    ):
        data = uri(case)
        if sheet:
            tile = f'<div class="tile sheet" role="img" aria-label="Animation de quatre trames" style="background-image:url({data})"></div>'
        else:
            height = 512 if case == "atlas-raster" else 128
            tile = f'<img class="tile" src="{data}" width="192" height="{height}" style="height:{height}px" alt="{escape(label)}">'
        tiles.append(f"<section><h2>{escape(label)}</h2>{tile}<p>{escape(note)}</p></section>")
    page = f"""<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ghostframe — avant et après traitement</title>
<style>{CSS}</style>
<header>
  <p class="brand">RESIDUAL LABS / GHOSTFRAME</p>
  <h1>Ce qui reste d’un PNG animé</h1>
  <p>Les six vues utilisent les octets produits par le service de test local. L’animation est rendue par le navigateur à l’ouverture de la page.</p>
</header>
<main>{''.join(tiles)}</main>
</html>
"""
    path.write_text(page, encoding="utf-8")


def build_capture_preview(path, captures, record):
    probes = {probe["name"]: probe["rect"] for probe in record["probes"]}
    selections = (
        ("APNG servi en image/png", "APNG natif"),
        ("APNG aplati", "APNG aplati"),
        ("Ghostframe restauré", "Ghostframe restauré"),
        ("Même atlas animé en CSS", "Atlas lu en CSS"),
    )
    font = ImageFont.load_default(size=14)
    sample_times = [sample["elapsed_ms"] for sample in record["samples"]]
    delays = [max(10, end - start) for start, end in zip(sample_times, sample_times[1:])]
    delays.append(delays[-1])
    frames = []
    for sample in record["samples"]:
        frame = Image.new("RGB", (608, 130), "#111a29")
        draw = ImageDraw.Draw(frame)
        with Image.open(captures / sample["file"]) as shot:
            for index, (name, label) in enumerate(selections):
                position = probes[name]
                x, y = position["x"], position["y"]
                tile = shot.crop((x, y, x + position["width"], y + position["height"]))
                left = 20 + index * 149
                draw.text((left, 22), label, font=font, fill="#eaf3fb")
                frame.paste(tile, (left, 48))
        frames.append(frame)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=delays, loop=0)
