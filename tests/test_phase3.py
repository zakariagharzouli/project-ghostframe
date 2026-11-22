import io
import struct
import unittest
import zlib

from PIL import Image

import ghostframe as gf
from pngcheck import ADAM7, describe, validate_png
from profile_fixtures import REFERENCE, compatibility_cases, demo_motion, raster_bytes, verify_original_pair
from profile_weight_pair import ANIMATED, SINGLE, STATIC, controls


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = compatibility_cases()
        cls.reports = {name: describe(blob) for name, (_, _, blob) in cls.cases.items()}

    def test_validate_all_pairs_and_dimensions(self):
        base = self.reports[REFERENCE]
        self.assertEqual(len(self.reports), 16)
        self.assertEqual(base["dimensions"], [320, 320])
        self.assertEqual(base["distinct_animation_frames"], 4)
        for key in ("IG03_apng_rectangles_320", "IG04_apng_poster_separe_320", "IG05_apng_gfRs_320",
                    "IG06_apng_rgb_320", "IG08_apng_sRGB_320", "IG09_apng_ICC_320", "IG10_apng_texte_320",
                    "IG11_apng_poids_320", "N01_apng_rgb_rectangles_320"):
            with self.subTest(key=key):
                result = self.reports[key]
                self.assertEqual(result["poster_sha256"], base["poster_sha256"])
                self.assertEqual(result["frames"], base["frames"])
                self.assertEqual(result["plays"], base["plays"])
        self.assertEqual(self.reports["LI02_apng_400"]["dimensions"], [400, 400])
        self.assertEqual(self.reports["LI04_apng_512"]["dimensions"], [512, 512])

    def test_archive_pair_and_statics_are_literal_binary_controls(self):
        standard = self.cases[REFERENCE][2]
        with_archive = self.cases["IG05_apng_gfRs_320"][2]
        self.assertTrue(verify_original_pair(with_archive, standard))
        raster = self.cases["IG01_statique_IDAT_320"][2]
        self.assertEqual(raster, raster_bytes(standard))
        self.assertEqual(describe(raster)["animation_frames"], 0)

    def test_exercised_factors(self):
        self.assertEqual(self.reports["IG06_apng_rgb_320"]["png"]["color_type"], 2)
        self.assertEqual(self.reports["IG07_apng_transparent_320"]["poster_alpha"], [0, 255])
        self.assertFalse(self.reports["IG04_apng_poster_separe_320"]["png"]["animation"]["default_in_animation"])
        self.assertEqual(self.reports["IG08_apng_sRGB_320"]["png"]["color_blocks"], ["sRGB"])
        self.assertEqual(self.reports["IG09_apng_ICC_320"]["png"]["color_blocks"], ["iCCP"])
        self.assertEqual(self.reports["IG10_apng_texte_320"]["png"]["metadata_blocks"], ["tEXt"])
        self.assertGreater(self.reports["IG11_apng_poids_320"]["bytes"], self.reports[REFERENCE]["bytes"])

    def test_equal_weight_pair_keeps_accepted_poster_and_idat(self):
        baseline = self.cases["IG01_statique_IDAT_320"][2]
        fixtures = controls(baseline)
        static, animated = (fixtures[name][2] for name in (STATIC, ANIMATED))
        clean, still, moving = map(describe, (baseline, static, animated))
        self.assertEqual(len(static), len(animated))
        self.assertEqual(raster_bytes(static), baseline)
        self.assertEqual(raster_bytes(animated), baseline)
        self.assertEqual(clean["poster_sha256"], moving["poster_sha256"])
        self.assertEqual(clean["poster_sha256"], still["poster_sha256"])
        self.assertEqual(still["png"]["metadata_blocks"], ["tEXt"])
        self.assertEqual(moving["distinct_animation_frames"], 2)
        single = fixtures[SINGLE][2]
        one = describe(single)
        self.assertEqual(len(single), len(animated))
        self.assertEqual(raster_bytes(single), baseline)
        self.assertEqual(one["animation_frames"], 1)
        self.assertEqual(one["frames"][0]["rgba_sha256"], clean["poster_sha256"])
        self.assertNotIn(b"fdAT", {kind for kind, _ in gf.chunks(single)})


class ValidatorTests(unittest.TestCase):
    def test_reports_apng_geometry_and_timing(self):
        result = validate_png(gf.apng(demo_motion(320), sparse=True))
        animation = result["animation"]
        self.assertEqual(animation["frames"][0]["rect"], [0, 0, 320, 320])
        self.assertEqual(animation["frames"][0]["delay"], [350, 1000])
        self.assertTrue(any(frame["rect"] != [0, 0, 320, 320] for frame in animation["frames"]))

    def test_rejects_bad_sequences_and_bad_scanline_filter_with_correct_crc(self):
        blob = gf.apng(demo_motion(320))
        altered = [(kind, struct.pack(">I", 42) + data[4:] if kind == b"fdAT" else data)
                   for kind, data in gf.chunks(blob)]
        with self.assertRaisesRegex(ValueError, "Séquence"):
            validate_png(gf.serialize(altered))
        tiny = gf.serialize([gf.header(1, 1), (b"IDAT", zlib.compress(b"\x05\x00\x00\x00\x00")), (b"IEND", b"")])
        with self.assertRaisesRegex(ValueError, "Filtre"):
            validate_png(tiny)

    def test_indexed_png_and_adam7(self):
        picture = Image.new("P", (9, 9), 2)
        picture.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0])
        file = io.BytesIO()
        picture.save(file, "PNG", bits=2, transparency=0)
        self.assertEqual(describe(file.getvalue())["png"]["color_type"], 3)
        side = 9
        scans = b"".join(b"\x00" + bytes(range(x, side, dx))
                         for x, y, dx, dy in ADAM7 for _ in range(y, side, dy) if x < side)
        header = b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 1)
        png = gf.serialize([header, (b"IDAT", zlib.compress(scans)), (b"IEND", b"")])
        self.assertEqual(describe(png)["png"]["interlace"], 1)


try:
    import cv2
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, "Installer requirements-phase2.txt pour l'audit de livraison")
class AttributionTests(unittest.TestCase):
    def test_distinguishes_loss_of_bytes_from_static_surface(self):
        from profile_diagnosis import DELIVERY_LOSS, NATIVE, RENDER_FIXED, compare

        blob = gf.apng(demo_motion(320))
        reference = describe(blob)
        checks = {"mime": "image/png", "delivery_verified": True, "standard_client": True}
        self.assertEqual(compare(blob, raster_bytes(blob), checks, [], True)["diagnosis"], DELIVERY_LOSS)
        times = range(0, 3001, 100)
        drawn = [{"size": [320, 320], "sha256": reference["poster_sha256"], "elapsed_ms": time} for time in times]
        self.assertEqual(compare(blob, blob, checks, drawn, True)["diagnosis"], RENDER_FIXED)
        shown = [{"size": [320, 320], "sha256": frame["rgba_sha256"], "elapsed_ms": index * 350}
                 for index, frame in enumerate(reference["frames"])]
        self.assertEqual(compare(blob, blob, checks, shown, True)["diagnosis"], NATIVE)
        checks["delivery_verified"] = False
        self.assertEqual(compare(blob, blob, checks, drawn, True)["diagnosis"], "indéterminé")

    def test_refuses_to_infer_static_render_from_synchronized_samples(self):
        from profile_diagnosis import compare

        motion = demo_motion(320)
        blob = gf.apng(motion)
        variant = {"delivery_verified": True, "mime": "image/png", "standard_client": True}
        captured = [{"size": [320, 320], "sha256": gf.digest(motion.frames[0]), "elapsed_ms": time}
                    for time in range(0, 4201, 1400)]
        result = compare(blob, blob, variant, captured, True)
        self.assertEqual(result["diagnosis"], "animation_livrée_rendu_indéterminé")
        self.assertFalse(result["render"]["coverage_two_loops"])


if __name__ == "__main__":
    unittest.main()
