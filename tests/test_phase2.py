import io
import struct
import tempfile
import unittest
from pathlib import Path

try:
    import cv2
except ImportError as error:
    raise unittest.SkipTest("Installer requirements-phase2.txt pour les tests Phase 2") from error

from PIL import Image, ImageDraw

import capsule
import ghostframe as gf
from audit_pair import compare
from lab import art, fixture_motion, local_lab, submit
from pipelines import TRANSFORMS, describe
from platform_lab import mime_probes, sparse_corpus


class SparseTests(unittest.TestCase):
    def test_difference_rectangles_keep_frames_and_delays(self):
        motion = sparse_corpus()
        sparse, full = gf.apng(motion, sparse=True), gf.apng(motion)
        self.assertLess(len(sparse), len(full) // 3)
        self.assertEqual(gf.decoded_png(sparse)[2], motion)
        rects = [struct.unpack(">IIIIIHHBB", data)[1:5] for kind, data in gf.chunks(sparse) if kind == b"fcTL"]
        self.assertEqual(rects[0], (384, 216, 0, 0))
        self.assertTrue(all(width == 26 and height == 19 for width, height, _, _ in rects[1:]))

    def test_source_can_clear_pixels_and_identical_frames_keep_their_delays(self):
        width, height = 96, 64
        opaque = art(0)
        cleared = bytearray(opaque)
        cleared[4:8] = b"\x00\x00\x00\x00"
        recolored = bytearray(cleared)
        recolored[8] ^= 0xFF
        motion = gf.Motion(width, height, (opaque, bytes(cleared), bytes(recolored), bytes(recolored)),
                           (230, 350, 370, 390), 2)
        poster = art(None)
        encoded = gf.apng(motion, poster=poster, archive=True, sparse=True)
        self.assertEqual(gf.decoded_png(encoded), ((width, height), poster, motion))
        self.assertEqual(gf.decoded_png(gf.recover(encoded))[2], motion)
        controls = [data for kind, data in gf.chunks(encoded) if kind == b"fcTL"]
        self.assertEqual(struct.unpack_from(">IIII", controls[-1], 4), (1, 1, 0, 0))


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        self.motion = fixture_motion()
        self.sheet = capsule.encode(self.motion)

    def test_crop_resize_and_jpeg_erase_one_shard(self):
        converted, suffix, mime = TRANSFORMS["cv-combined"](self.sheet)
        recovered = capsule.decode(converted)
        self.assertEqual((suffix, mime), ("jpg", "image/jpeg"))
        self.assertEqual(recovered.motion, self.motion)
        self.assertEqual(recovered.valid_shards, (1, 2, 3))
        self.assertEqual(recovered.repaired_index, 0)

    def test_invalid_visual_tile_is_repaired_by_parity(self):
        with Image.open(io.BytesIO(self.sheet)) as image:
            ImageDraw.Draw(image).rectangle((48, 48, 90, 90), fill="white")
            output = io.BytesIO()
            image.save(output, "PNG")
        restored = capsule.decode(output.getvalue())
        self.assertEqual(restored.motion, self.motion)
        self.assertEqual(restored.repaired_index, 0)

    def test_insufficient_resolution_data_or_chroma_is_rejected(self):
        for operation in ("cv-crop-half", "cv-tiny", "cv-gray"):
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "non récupérable"):
                capsule.decode(TRANSFORMS[operation](self.sheet)[0])


class PipelineTests(unittest.TestCase):
    def test_cv_entry_points_have_different_temporal_results(self):
        motion = fixture_motion()
        source = gf.apng(motion, poster=art(None), archive=True, sparse=True)
        still = TRANSFORMS["cv-raster"](source)[0]
        animated = TRANSFORMS["cv-animation"](source)[0]
        self.assertIsNone(gf.decoded_png(still)[2])
        self.assertEqual(gf.decoded_png(animated), ((96, 64), art(None), motion))
        self.assertNotIn(b"gfRs", [kind for kind, _ in gf.chunks(animated)])

    def test_webp_transcodes_the_reference_without_changing_motion(self):
        motion = fixture_motion()
        source = gf.apng(motion, sparse=True)
        with local_lab(TRANSFORMS) as (base, _):
            output, http = submit(base, source, "pillow-webp")
            controls = mime_probes(base, source)
        self.assertEqual((http["content_type"], http["upload_status"]), ("image/webp", 201))
        self.assertEqual(describe(output)[0]["motion"], motion.fingerprint())
        self.assertEqual([probe["upload_status"] for probe in controls], [415, 422, 422])

    def test_external_pair_needs_both_bytes_and_client_evidence(self):
        motion = fixture_motion()
        source = gf.apng(motion)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, delivered = root / "input.png", root / "output.png"
            original.write_bytes(source)
            delivered.write_bytes(source)
            receipt = {"accepted_as_png": True, "delivery_mime": "image/png", "standard_client": True}
            self.assertEqual(compare(original, delivered, receipt, root)["native_result"], "indéterminé")
            frames = []
            for index, frame in enumerate(motion.frames):
                name = f"capture-{index}.png"
                (root / name).write_bytes(gf.static_png(96, 64, frame))
                frames.append({"file": name, "elapsed_ms": index * 350})
            receipt["captures"] = frames
            self.assertEqual(compare(original, delivered, receipt, root)["native_result"], "succès")
            delivered.write_bytes((root / "capture-0.png").read_bytes())
            receipt["captures"] = [{"file": "capture-0.png", "elapsed_ms": time} for time in (0, 1000, 3000)]
            self.assertEqual(compare(original, delivered, receipt, root)["native_result"], "échec")


if __name__ == "__main__":
    unittest.main()
