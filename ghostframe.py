"""PNG encoding and transport experiments for full-frame RGBA animations."""

import argparse
import hashlib
import io
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

SIGNATURE = b"\x89PNG\r\n\x1a\n"
ARCHIVE = b"gfRs"
ARCHIVE_HEADER = struct.Struct(">4sHHHI32s")
MAX_FILE = 32 * 1024 * 1024
MAX_MOTION = 32 * 1024 * 1024
MAX_PIXELS = 4_000_000
MAX_FRAMES = 120


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rgba_length(width, height):
    if not (0 < width <= 65535 and 0 < height <= 65535):
        raise ValueError("Dimensions hors limites")
    if width * height > MAX_PIXELS:
        raise ValueError("Raster trop grand")
    return width * height * 4


@dataclass(frozen=True)
class Motion:
    width: int
    height: int
    frames: tuple[bytes, ...]
    delays: tuple[int, ...]
    plays: int = 0

    def __post_init__(self):
        size = rgba_length(self.width, self.height)
        if not 1 <= len(self.frames) <= MAX_FRAMES or len(self.frames) * size > MAX_MOTION:
            raise ValueError("Nombre ou volume de trames hors limites")
        if any(len(frame) != size for frame in self.frames):
            raise ValueError("Dimensions de trames incohérentes")
        if len(self.frames) != len(self.delays) or any(
            not isinstance(ms, int) or not 1 <= ms <= 65535 for ms in self.delays
        ):
            raise ValueError("Délais entiers en millisecondes attendus")
        if not 0 <= self.plays <= 0xFFFFFFFF:
            raise ValueError("Nombre de lectures hors limites")

    def fingerprint(self):
        return {
            "size": [self.width, self.height],
            "frames": [digest(frame) for frame in self.frames],
            "delays_ms": list(self.delays),
            "plays": self.plays,
        }


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def chunks(blob):
    """Validate bounded PNG framing and return chunk types and payloads."""
    if len(blob) > MAX_FILE or not blob.startswith(SIGNATURE):
        raise ValueError("Signature ou taille PNG invalide")
    stream = []
    pos = len(SIGNATURE)
    while pos + 12 <= len(blob):
        length, kind = struct.unpack_from(">I4s", blob, pos)
        end = pos + 12 + length
        if end > len(blob) or not kind.isalpha() or not kind[2:3].isupper():
            raise ValueError("Bloc PNG invalide")
        data = blob[pos + 8:end - 4]
        if zlib.crc32(kind + data) != struct.unpack_from(">I", blob, end - 4)[0]:
            raise ValueError(f"CRC invalide pour {kind.decode('ascii')}")
        if len(stream) == 8192:
            raise ValueError("Trop de blocs PNG")
        stream.append((kind, data))
        pos = end
        if kind == b"IEND":
            break
    kinds = [kind for kind, _ in stream]
    if (
        pos != len(blob) or not kinds or kinds[0] != b"IHDR"
        or kinds[-1] != b"IEND" or stream[-1][1]
        or kinds.count(b"IHDR") != 1 or len(stream[0][1]) != 13
        or b"IDAT" not in kinds
    ):
        raise ValueError("Structure PNG incomplète")
    first = kinds.index(b"IDAT")
    if kinds[first:first + kinds.count(b"IDAT")] != [b"IDAT"] * kinds.count(b"IDAT"):
        raise ValueError("Blocs IDAT non contigus")
    rgba_length(*struct.unpack_from(">II", stream[0][1]))
    return stream


def serialize(stream):
    blob = SIGNATURE + b"".join(png_chunk(kind, data) for kind, data in stream)
    if len(blob) > MAX_FILE:
        raise ValueError("Fichier PNG trop grand")
    return blob


def compressed_pixels(width, height, rgba, *, rgb=False, level=9):
    if rgba_length(width, height) != len(rgba):
        raise ValueError("Taille du raster incohérente")
    if rgb and rgba[3::4].count(255) != width * height:
        raise ValueError("Le mode RGB exige des pixels opaques")
    pixels = Image.frombytes("RGBA", (width, height), rgba).convert("RGB").tobytes() if rgb else rgba
    stride = width * (3 if rgb else 4)
    rows = (b"\x00" + pixels[offset:offset + stride] for offset in range(0, len(pixels), stride))
    return zlib.compress(b"".join(rows), level=level)


def header(width, height, *, rgb=False):
    return b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2 if rgb else 6, 0, 0, 0)


def static_png(width, height, rgba, *, rgb=False):
    return serialize([
        header(width, height, rgb=rgb), (b"IDAT", compressed_pixels(width, height, rgba, rgb=rgb)), (b"IEND", b""),
    ])


def frame_region(width, height, frame, previous, full_pixels, *, rgb, level):
    current = Image.frombytes("RGBA", (width, height), frame)
    prior = Image.frombytes("RGBA", (width, height), previous)
    box = ImageChops.difference(current, prior).getbbox(alpha_only=False)
    left, top, right, bottom = box or (0, 0, 1, 1)
    cropped_width, cropped_height = right - left, bottom - top
    if (cropped_width, cropped_height) != (width, height):
        compressed = compressed_pixels(cropped_width, cropped_height, current.crop((left, top, right, bottom)).tobytes(),
                                       rgb=rgb, level=level)
        if len(compressed) < len(full_pixels):
            return cropped_width, cropped_height, left, top, compressed
    return width, height, 0, 0, full_pixels


def apng(motion, poster=None, archive=False, sparse=False, *, rgb=False, level=9):
    """Use a separate default image when poster is supplied."""
    width, height = motion.width, motion.height
    stream = [header(width, height, rgb=rgb), (b"acTL", struct.pack(">II", len(motion.frames), motion.plays))]
    if poster is not None:
        stream.append((b"IDAT", compressed_pixels(width, height, poster, rgb=rgb, level=level)))

    sequence = 0
    previous = None
    for index, (frame, delay) in enumerate(zip(motion.frames, motion.delays, strict=True)):
        region_width, region_height, x, y = width, height, 0, 0
        pixels = compressed_pixels(width, height, frame, rgb=rgb, level=level)
        if sparse and previous is not None:
            region_width, region_height, x, y, pixels = frame_region(width, height, frame, previous, pixels,
                                                                   rgb=rgb, level=level)
        control = struct.pack(">IIIIIHHBB", sequence, region_width, region_height, x, y, delay, 1000, 0, 0)
        stream.append((b"fcTL", control))
        sequence += 1
        if index == 0 and poster is None:
            stream.append((b"IDAT", pixels))
        else:
            stream.append((b"fdAT", struct.pack(">I", sequence) + pixels))
            sequence += 1
        previous = frame
    if archive:
        default = motion.frames[0] if poster is None else poster
        stream.append((ARCHIVE, archive_payload(motion, default)))
    stream.append((b"IEND", b""))
    return serialize(stream)


def xor_frame(frame, previous):
    return bytes(a ^ b for a, b in zip(frame, previous, strict=True))


def archive_payload(motion, poster):
    if len(poster) != rgba_length(motion.width, motion.height):
        raise ValueError("Dimensions de l’image par défaut incohérentes")
    header_bytes = ARCHIVE_HEADER.pack(
        b"GFR1", motion.width, motion.height, len(motion.frames), motion.plays,
        hashlib.sha256(poster).digest(),
    )
    delays = struct.pack(f">{len(motion.delays)}H", *motion.delays)
    residuals = [motion.frames[0]]
    for previous, frame in zip(motion.frames, motion.frames[1:]):
        residuals.append(xor_frame(frame, previous))
    return header_bytes + zlib.compress(delays + b"".join(residuals), level=9)


def read_archive(payload):
    if len(payload) <= ARCHIVE_HEADER.size:
        raise ValueError("Archive Ghostframe tronquée")
    magic, width, height, count, plays, poster_hash = ARCHIVE_HEADER.unpack_from(payload)
    size = rgba_length(width, height)
    if magic != b"GFR1" or not 1 <= count <= MAX_FRAMES or count * size > MAX_MOTION:
        raise ValueError("En-tête Ghostframe invalide")
    expected = count * (size + 2)
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(payload[ARCHIVE_HEADER.size:], expected + 1)
    if len(decoded) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Taille ou flux Ghostframe invalide")
    delays = struct.unpack_from(f">{count}H", decoded)
    frames = []
    for offset in range(count * 2, expected, size):
        residual = decoded[offset:offset + size]
        frames.append(xor_frame(residual, frames[-1]) if frames else residual)
    return Motion(width, height, tuple(frames), delays, plays), poster_hash


def decoded_png(blob):
    """Decode the default raster and, when present, full composited APNG frames."""
    stream = chunks(blob)
    with Image.open(io.BytesIO(blob), formats=["PNG"]) as image:
        width, height = image.size
        default = image.convert("RGBA").tobytes()
        motion = None
        if any(kind == b"acTL" for kind, _ in stream):
            start = int(bool(image.info.get("default_image")))
            count = image.n_frames - start
            plays = image.info.get("loop", 0)
            if not 1 <= count <= MAX_FRAMES or count * rgba_length(width, height) > MAX_MOTION:
                raise ValueError("Animation hors limites")
            frames, delays = [], []
            for index in range(start, image.n_frames):
                image.seek(index)
                frames.append(image.convert("RGBA").tobytes())
                delays.append(round(image.info["duration"]))
            motion = Motion(width, height, tuple(frames), tuple(delays), plays)
    return (width, height), default, motion


def inspect(blob):
    stream = chunks(blob)
    size, default, motion = decoded_png(blob)
    return {
        "sha256": digest(blob),
        "bytes": len(blob),
        "size": list(size),
        "default_sha256": digest(default),
        "chunks": [kind.decode("ascii") for kind, _ in stream],
        "archive_bytes": sum(len(payload) for kind, payload in stream if kind == ARCHIVE),
        "motion": None if motion is None else motion.fingerprint(),
    }


def recover(blob):
    archives = [payload for kind, payload in chunks(blob) if kind == ARCHIVE]
    if len(archives) != 1:
        raise ValueError("Un seul bloc Ghostframe est requis")
    motion, poster_hash = read_archive(archives[0])
    size, poster, _ = decoded_png(blob)
    if size != (motion.width, motion.height) or hashlib.sha256(poster).digest() != poster_hash:
        raise ValueError("Le raster par défaut ne correspond plus à l’archive")
    separate_poster = None if poster == motion.frames[0] else poster
    return apng(motion, poster=separate_poster)


def atlas(motion):
    height = motion.height * len(motion.frames)
    pixels = b"".join(motion.frames)
    blob = static_png(motion.width, height, pixels)
    manifest = motion.fingerprint()
    manifest["atlas_rgba_sha256"] = digest(pixels)
    return blob, manifest


def from_atlas(blob, manifest):
    width, height = manifest["size"]
    hashes = manifest["frames"]
    stride = rgba_length(width, height)
    size, pixels, native_motion = decoded_png(blob)
    if native_motion is not None or size != (width, height * len(hashes)):
        raise ValueError("Dimensions de l’atlas inattendues")
    if digest(pixels) != manifest["atlas_rgba_sha256"]:
        raise ValueError("Les pixels de l’atlas ont changé")
    frames = tuple(pixels[start:start + stride] for start in range(0, len(pixels), stride))
    if [digest(frame) for frame in frames] != hashes:
        raise ValueError("Les trames de l’atlas ne correspondent pas au manifeste")
    return Motion(width, height, frames, tuple(manifest["delays_ms"]), manifest["plays"])


def encode_files(paths, delay, plays):
    size, frames = None, []
    if len(paths) > MAX_FRAMES:
        raise ValueError("Trop de fichiers source")
    for path in paths:
        frame_size, pixels, motion = decoded_png(path.read_bytes())
        if motion is not None or (size is not None and size != frame_size):
            raise ValueError("Des PNG statiques aux dimensions identiques sont requis")
        size = frame_size
        if (len(frames) + 1) * len(pixels) > MAX_MOTION:
            raise ValueError("Séquence trop volumineuse")
        frames.append(pixels)
    return Motion(*size, tuple(frames), (delay,) * len(frames), plays)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    encode = commands.add_parser("encode")
    encode.add_argument("output", type=Path)
    encode.add_argument("frames", type=Path, nargs="+")
    encode.add_argument("--delay", type=int, default=250)
    encode.add_argument("--plays", type=int, default=0)
    encode.add_argument("--mode", choices=["apng", "dual", "atlas"], default="dual")
    encode.add_argument("--sparse", action="store_true", help="Rectangles de différences APNG")
    show = commands.add_parser("inspect")
    show.add_argument("input", type=Path)
    restore = commands.add_parser("recover")
    restore.add_argument("input", type=Path)
    restore.add_argument("output", type=Path)
    split = commands.add_parser("from-atlas")
    split.add_argument("input", type=Path)
    split.add_argument("manifest", type=Path)
    split.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            print(json.dumps(inspect(args.input.read_bytes()), indent=2))
        elif args.command == "recover":
            args.output.write_bytes(recover(args.input.read_bytes()))
        elif args.command == "from-atlas":
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            args.output.write_bytes(apng(from_atlas(args.input.read_bytes(), manifest)))
        else:
            motion = encode_files(args.frames, args.delay, args.plays)
            if args.mode == "atlas":
                if args.sparse:
                    raise ValueError("--sparse exige un mode APNG ou dual")
                blob, manifest = atlas(motion)
                args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            else:
                blob = apng(motion, archive=args.mode == "dual", sparse=args.sparse)
            args.output.write_bytes(blob)
    except (ValueError, KeyError, TypeError, OSError, SyntaxError, EOFError, zlib.error, struct.error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
