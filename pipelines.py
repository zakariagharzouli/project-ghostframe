"""Adapters for the pinned open-source codecs used in phase 2."""

import io
from functools import partial

import cv2
import numpy as np
from PIL import Image, features

import ghostframe as gf

FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp")}


def describe(blob):
    if len(blob) > gf.MAX_FILE:
        raise ValueError("Fichier trop volumineux")
    with Image.open(io.BytesIO(blob), formats=list(FORMATS)) as image:
        width, height = image.size
        gf.rgba_length(width, height)
        name, mode = image.format, image.mode
        profile = image.info.get("icc_profile")
        initial = image.convert("RGBA").tobytes()
        motion = None
        if name == "PNG":
            png = gf.inspect(blob)
            blocks = gf.chunks(blob)
            ihdr = blocks[0][1]
            color = {
                "mode": mode, "png_bit_depth": ihdr[8], "png_color_type": ihdr[9],
                "icc_sha256": gf.digest(profile) if profile else None,
            }
            ancillary = [
                {"type": kind.decode(), "bytes": len(payload), "sha256": gf.digest(payload)}
                for kind, payload in blocks if kind[:1].islower()
            ]
            motion = png["motion"]
        else:
            png, ancillary = None, None
            color = {"mode": mode, "icc_sha256": gf.digest(profile) if profile else None}
            count = getattr(image, "n_frames", 1)
            if count > 1:
                plays = image.info.get("loop", 0)
                frames, delays = [], []
                if count > gf.MAX_FRAMES or len(initial) * count > gf.MAX_MOTION:
                    raise ValueError("Animation hors limites")
                for index in range(count):
                    image.seek(index)
                    frames.append(gf.digest(image.convert("RGBA").tobytes()))
                    delays.append(image.info.get("duration"))
                motion = {"size": [width, height], "frames": frames, "delays_ms": delays, "plays": plays}
    return {
        "sha256": gf.digest(blob), "bytes": len(blob), "format": name, "size": [width, height],
        "default_sha256": gf.digest(initial), "color": color, "motion": motion,
        "png_chunks": png["chunks"] if png else None, "png_ancillary": ancillary,
    }, initial


def changes(before, after, before_pixels, after_pixels):
    by_chunk = after["png_ancillary"] or []
    before_chunks = before["png_ancillary"] or []
    kept = [block for block in before_chunks if block in by_chunk]
    changed = [block for block in before_chunks if block not in kept and any(
        later["type"] == block["type"] for later in by_chunk
    )]
    result = {
        "same_file": before["sha256"] == after["sha256"],
        "same_default_pixels": before["default_sha256"] == after["default_sha256"],
        "same_dimensions": before["size"] == after["size"],
        "same_color_description": before["color"] == after["color"],
        "same_motion": before["motion"] is not None and before["motion"] == after["motion"],
        "ancillary_retained_verbatim": kept, "ancillary_changed": changed,
        "ancillary_removed": [block for block in before_chunks if block not in kept and block not in changed],
        "changed_pixels": None, "max_channel_delta": None,
    }
    if result["same_dimensions"]:
        a = np.frombuffer(before_pixels, np.uint8).reshape(-1, 4)
        b = np.frombuffer(after_pixels, np.uint8).reshape(-1, 4)
        result["changed_pixels"] = int(np.count_nonzero(np.any(a != b, axis=1)))
        result["max_channel_delta"] = int(np.max(np.abs(a.astype(np.int16) - b)))
    return result


def opencv(blob, operation):
    buffer = np.frombuffer(blob, np.uint8)
    if operation == "animation":
        success, sequence = cv2.imdecodeanimation(buffer, 0, gf.MAX_FRAMES)
        if not success:
            raise ValueError("OpenCV n'a pas décodé l'animation")
        success, output = cv2.imencodeanimation(".png", sequence)
        mime, suffix = "image/png", "png"
    else:
        image = cv2.imdecode(buffer, cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError("OpenCV n'a pas décodé le raster")
        height, width = image.shape[:2]
        if operation in ("crop-one", "combined"):
            left = width // 4 + min(11, width // 10)
            top = min(5, height // 8)
            image = image[top:height - top, left:width]
        elif operation == "crop-half":
            image = image[:, width // 4:width - width // 4]
        if operation in ("resize", "tiny", "combined"):
            divisor = 8 if operation == "tiny" else 2
            height, width = image.shape[:2]
            image = cv2.resize(image, (max(1, width // divisor), max(1, height // divisor)),
                               interpolation=cv2.INTER_AREA)
        if operation == "gray" and image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if operation in ("jpeg", "combined"):
            success, output = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 65])
            mime, suffix = "image/jpeg", "jpg"
        else:
            success, output = cv2.imencode(".png", image)
            mime, suffix = "image/png", "png"
    if not success:
        raise ValueError("Échec du réencodage OpenCV")
    return output.tobytes(), suffix, mime


def webp(blob):
    _, default, motion = gf.decoded_png(blob)
    if motion is None:
        raise ValueError("Animation requise pour le transcodage WebP")
    if default != motion.frames[0]:
        raise ValueError("Ce profil WebP exige un poster commun à la première trame")
    shape = motion.width, motion.height
    frames = [Image.frombytes("RGBA", shape, frame) for frame in motion.frames]
    buffer = io.BytesIO()
    frames[0].save(buffer, "WEBP", save_all=True, append_images=frames[1:], duration=motion.delays,
                   loop=motion.plays, lossless=True, exact=True)
    return buffer.getvalue(), "webp", "image/webp"


def versions():
    return {"opencv": cv2.__version__, "numpy": np.__version__, "libwebp": features.version("webp")}


TRANSFORMS = {
    **{f"cv-{name}": partial(opencv, operation=name) for name in
       ("raster", "animation", "resize", "crop-one", "crop-half", "jpeg", "combined", "tiny", "gray")},
    "pillow-webp": webp,
}
