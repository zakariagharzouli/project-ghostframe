"""Mesure la négociation HTTP d'un avatar Instagram annoncé sur un profil public."""

import argparse
import json
import re
import zlib
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import ImageCms

from pngcheck import describe, must

ACCEPT_CASES = (
    ("toutes-images", "image/*"),
    ("préférences-mixtes", "image/avif,image/webp,image/apng,image/png,image/*;q=0.8"),
    ("png-apng", "image/apng,image/png"),
    ("webp", "image/webp"),
    ("avif", "image/avif"),
)
MAX_RESPONSE = 4 * 1024 * 1024


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProfileMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og_image = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "meta" and fields.get("property") == "og:image":
            self.og_image = fields.get("content")


def is_cdn_image(url):
    address = urlsplit(url)
    return (
        address.scheme == "https"
        and (address.hostname or "").endswith(".cdninstagram.com")
        and not address.username and not address.password
        and address.path.startswith("/v/")
    )


def avatar_url(html):
    metadata = ProfileMetadata()
    metadata.feed(html)
    must(metadata.og_image and is_cdn_image(metadata.og_image), "Image og:image du profil introuvable")
    image_path = urlsplit(metadata.og_image).path
    for match in re.finditer(r'"profile_pic_url"\s*:\s*("(?:[^"\\]|\\.)*")', html):
        candidate = json.loads(match[1])
        if is_cdn_image(candidate) and urlsplit(candidate).path == image_path:
            return candidate
    raise ValueError("Aucun profile_pic_url correspondant à og:image dans la page publique")


def get(opener, url, accept):
    try:
        response = opener.open(Request(url, headers={"Accept": accept}), timeout=15)
    except HTTPError as error:
        with error:
            return error.code, error.headers, b""
    with response:
        body = response.read(MAX_RESPONSE + 1)
        must(len(body) <= MAX_RESPONSE, "Réponse supérieure à 4 Mio")
        return response.status, response.headers, body


def classify(body, content_type):
    result = describe(body)
    actual = result["mime_from_bytes"]
    matches = content_type == actual or (
        content_type == "image/apng" and actual == "image/png" and result["animation_frames"] > 0
    )
    return {
        "format": result["format"], "dimensions": result["dimensions"], "bytes": result["bytes"],
        "sha256": result["sha256"], "animation_frames": result["animation_frames"],
        "distinct_animation_frames": result["distinct_animation_frames"],
        "diagnosis": ("multiframe" if result["distinct_animation_frames"] > 1 else "statique")
        if matches else "indéterminé",
    }


def probe(username):
    must(re.fullmatch(r"[a-zA-Z0-9._]{1,30}", username) and username not in (".", ".."),
         "Nom de profil Instagram invalide")
    profile = f"https://www.instagram.com/{username}/"
    opener = build_opener(NoRedirects())
    code, _, html = get(opener, profile, "text/html")
    must(code == 200, f"Page publique indisponible (HTTP {code})")
    asset = avatar_url(html.decode("utf-8", "replace"))
    requests = []
    for name, accept in ACCEPT_CASES:
        code, headers, body = get(opener, asset, accept)
        mime = headers.get_content_type()
        row = {"case": name, "accept": accept, "http_status": code, "content_type": mime,
               "vary": headers.get("Vary"), "diagnosis": "indéterminé"}
        if code == 200:
            try:
                row.update(classify(body, mime))
            except (ValueError, SyntaxError, EOFError, OSError, zlib.error, ImageCms.PyCMSError) as error:
                row["decode_error"] = str(error)
        requests.append(row)
        if code in (401, 403, 429):
            break
    return {
        "measured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "profile": profile, "selected_reference": "profile_pic_url correspondant à og:image",
        "cdn_host": urlsplit(asset).hostname, "requests": requests,
        "identical_image_bytes": len({row.get("sha256") for row in requests}) == 1
        if len(requests) == len(ACCEPT_CASES) and all("sha256" in row for row in requests) else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Nom du profil public examiné")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = probe(args.username)
    except (ValueError, URLError, TimeoutError) as error:
        parser.exit(2, f"{error}\n")
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(encoded, encoding="utf-8", newline="\n")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
