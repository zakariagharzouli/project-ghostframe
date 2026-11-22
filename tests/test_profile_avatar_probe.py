import json
import unittest
from email.message import Message
from unittest.mock import patch

import ghostframe as gf
from profile_avatar_probe import ACCEPT_CASES, avatar_url, classify, probe

META = "https://scontent.cdninstagram.com/v/photo.jpg?variant=150&amp;token=one"
PROFILE_PHOTO = "https://scontent.cdninstagram.com/v/photo.jpg?variant=150&token=two"
OTHER_PHOTO = "https://other.cdninstagram.com/v/other.jpg?variant=150"


def page(*urls):
    profile_fields = ",".join(json.dumps({"profile_pic_url": url}) for url in urls)
    return f'<meta property="og:image" content="{META}"><script>[{profile_fields}]</script>'


class PublicAvatarTests(unittest.TestCase):
    def test_selects_the_matching_avatar_and_preserves_its_url(self):
        self.assertEqual(avatar_url(page(OTHER_PHOTO, PROFILE_PHOTO)), PROFILE_PHOTO)
        with self.assertRaisesRegex(ValueError, "correspondant"):
            avatar_url(page(OTHER_PHOTO))

    def test_requires_matching_mime_and_distinct_animation_frames(self):
        first = bytes((0, 0, 0, 255))
        second = bytes((255, 0, 0, 255))
        animated = gf.apng(gf.Motion(1, 1, (first, second), (500, 500)))
        repeated = gf.apng(gf.Motion(1, 1, (first, first), (500, 500)))
        self.assertEqual(classify(animated, "image/apng")["diagnosis"], "multiframe")
        self.assertEqual(classify(animated, "image/jpeg")["diagnosis"], "indéterminé")
        self.assertEqual(classify(repeated, "image/png")["diagnosis"], "statique")

    def test_report_reuses_the_announced_url_for_every_header(self):
        png = gf.static_png(1, 1, bytes((0, 0, 0, 255)))
        headers = Message()
        headers["Content-Type"] = "image/png"
        headers["Vary"] = "Accept"
        responses = [(200, Message(), page(PROFILE_PHOTO).encode())]
        responses.extend((200, headers, png) for _ in ACCEPT_CASES)
        with patch("profile_avatar_probe.get", side_effect=responses) as get:
            result = probe("residual.labs")
        self.assertTrue(result["identical_image_bytes"])
        self.assertEqual([row["diagnosis"] for row in result["requests"]], ["statique"] * len(ACCEPT_CASES))
        self.assertEqual([call.args[1] for call in get.call_args_list[1:]], [PROFILE_PHOTO] * len(ACCEPT_CASES))
        self.assertEqual([call.args[2] for call in get.call_args_list[1:]], [accept for _, accept in ACCEPT_CASES])


if __name__ == "__main__":
    unittest.main()
