import io
import tempfile
import unittest
import zlib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

import ghostframe as gf
from lab import art, fixture_motion, fixtures, local_lab, submit, transform


class GhostframeTests(unittest.TestCase):
    def setUp(self):
        self.motion = fixture_motion()
        self.dual = gf.apng(self.motion, archive=True)

    def test_native_apng_is_png_with_expected_frames(self):
        with Image.open(io.BytesIO(self.dual)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.n_frames, 4)
        self.assertEqual(gf.decoded_png(self.dual)[2], self.motion)
        sequence = [int.from_bytes(data[:4], "big") for kind, data in gf.chunks(self.dual)
                    if kind in (b"fcTL", b"fdAT")]
        self.assertEqual(sequence, list(range(7)))

    def test_separate_poster_survives_recovery(self):
        poster = art(None)
        source = gf.apng(self.motion, poster=poster, archive=True)
        restored = gf.recover(transform(source, "safe-copy"))
        with Image.open(io.BytesIO(restored)) as image:
            self.assertTrue(image.info["default_image"])
            self.assertEqual(image.n_frames, 5)
        self.assertEqual(gf.decoded_png(restored), ((96, 64), poster, self.motion))

    def test_nonuniform_delays_alpha_and_finite_loop_round_trip(self):
        source = gf.Motion(2, 1, (b"\x80\x42\x21\x60" * 2, b"\x21\x42\x80\xff" * 2), (125, 1700), 5)
        recovered = gf.recover(transform(gf.apng(source, archive=True), "safe-copy"))
        self.assertEqual(gf.decoded_png(recovered)[2], source)

    def test_chunk_only_transport_stays_static_until_rehydrated(self):
        retained = transform(self.dual, "safe-copy")
        report = gf.inspect(retained)
        self.assertEqual(report["chunks"], ["IHDR", "IDAT", "gfRs", "IEND"])
        self.assertIsNone(report["motion"])
        self.assertEqual(gf.recover(retained), gf.apng(self.motion))

    def test_rejects_archive_rebound_to_different_pixels(self):
        changed = transform(gf.apng(self.motion, poster=art(None)), "raster")
        stream = gf.chunks(changed)
        archive = next(item for item in gf.chunks(self.dual) if item[0] == gf.ARCHIVE)
        with self.assertRaisesRegex(ValueError, "ne correspond plus"):
            gf.recover(gf.serialize([*stream[:-1], archive, stream[-1]]))

    def test_rejects_missing_or_duplicate_archive(self):
        without = transform(self.dual, "raster")
        retained = gf.chunks(transform(self.dual, "safe-copy"))
        double = gf.serialize([*retained[:-1], retained[-2], retained[-1]])
        for source in (without, double):
            with self.subTest(length=len(source)), self.assertRaisesRegex(ValueError, "Un seul bloc"):
                gf.recover(source)

    def test_rejects_invalid_archive_stream(self):
        payload = gf.archive_payload(self.motion, self.motion.frames[0])
        for changed in (
            payload[:-1],
            payload + zlib.compress(b""),
            payload[:gf.ARCHIVE_HEADER.size] + zlib.compress(bytes(100_000)),
        ):
            with self.subTest(length=len(changed)), self.assertRaises((ValueError, zlib.error)):
                gf.read_archive(changed)

    def test_rejects_corrupted_crc_and_trailing_data(self):
        corrupted = bytearray(self.dual)
        corrupted[29] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC"):
            gf.chunks(corrupted)
        with self.assertRaisesRegex(ValueError, "Structure"):
            gf.chunks(self.dual + b"\x00")

    def test_atlas_survives_exact_raster_encoding(self):
        atlas, manifest = gf.atlas(self.motion)
        rewritten = transform(atlas, "raster")
        self.assertNotEqual(atlas, rewritten)
        self.assertEqual(gf.from_atlas(rewritten, manifest), self.motion)

    def test_atlas_rejects_resize_and_pixel_changes(self):
        atlas, manifest = gf.atlas(self.motion)
        with self.assertRaisesRegex(ValueError, "Dimensions"):
            gf.from_atlas(transform(atlas, "resize"), manifest)
        size, default, _ = gf.decoded_png(atlas)
        changed = gf.static_png(*size, bytes([default[0] ^ 1]) + default[1:])
        with self.assertRaisesRegex(ValueError, "pixels"):
            gf.from_atlas(changed, manifest)

    def test_two_distinct_inputs_collapse_to_identical_output(self):
        with tempfile.TemporaryDirectory() as directory:
            files, _ = fixtures(Path(directory))
        self.assertNotEqual(gf.inspect(files["apng-a"])["motion"], gf.inspect(files["apng-b"])["motion"])
        self.assertEqual(transform(files["apng-a"], "raster"), transform(files["apng-b"], "raster"))


class HTTPTests(unittest.TestCase):
    def test_response_mime_and_payload_and_rejection(self):
        blob = gf.apng(fixture_motion())
        with local_lab() as (base, _):
            stored, result = submit(base, blob, "copy")
            self.assertEqual(stored, blob)
            self.assertEqual(result["upload_status"], 201)
            self.assertEqual(result["download_status"], 200)
            self.assertEqual(result["content_type"], "image/png")
            for body, mime, status in (
                (blob, "image/gif", 415),
                (b"not a PNG", "image/png", 422),
            ):
                request = Request(f"{base}/upload/copy", data=body, headers={"Content-Type": mime})
                with self.subTest(status=status), self.assertRaises(HTTPError) as raised:
                    urlopen(request, timeout=5)
                self.assertEqual(raised.exception.code, status)


if __name__ == "__main__":
    unittest.main()
