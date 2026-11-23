import glob
import mimetypes
import os
import re
from functools import lru_cache
from urllib.parse import unquote, urlparse

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
HTML_PATH = os.path.join(WEB_DIR, "flip7.html")
ASSET_EXTENSIONS = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".woff", ".woff2",
)
TAG_RE = re.compile(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.I)
URL_RE = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.I)
QUOTED_RE = re.compile(r"['\"]([^'\"]+\.(?:js|css|png|jpg|jpeg|webp|svg|woff|woff2))['\"]", re.I)


def _clean(value):
    value = value.strip()
    if not value or value.startswith(("http://", "https://", "data:", "#", "//")):
        return ""
    if "+" in value or "${" in value or "<" in value:
        return ""
    path = unquote(urlparse(value).path).lstrip("/")
    if not path.lower().endswith(ASSET_EXTENSIONS):
        return ""
    if "/" not in path and not os.path.isfile(os.path.join(WEB_DIR, path)):
        matches = glob.glob(os.path.join(WEB_DIR, "**", os.path.basename(path)), recursive=True)
        files = [match for match in matches if os.path.isfile(match)]
        if len(files) == 1:
            return os.path.relpath(files[0], WEB_DIR)
    return path


@lru_cache(maxsize=None)
def referenced_assets():
    found = set()
    sources = [HTML_PATH]
    for name in os.listdir(WEB_DIR):
        if name.endswith((".js", ".css")):
            sources.append(os.path.join(WEB_DIR, name))
    for path in sources:
        try:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
        except OSError:
            continue
        for match in TAG_RE.findall(text):
            asset = _clean(match)
            if asset:
                found.add(asset)
        for match in URL_RE.findall(text):
            asset = _clean(match)
            if asset:
                found.add(asset)
        for match in QUOTED_RE.findall(text):
            asset = _clean(match)
            if asset:
                found.add(asset)
    return frozenset(found)


def content_type(path):
    guessed, _ = mimetypes.guess_type(path)
    if guessed:
        return guessed
    if path.endswith(".js"):
        return "text/javascript"
    return "application/octet-stream"


def resolve(path):
    asset = _clean(path)
    if not asset or asset not in referenced_assets():
        return None
    full = os.path.normpath(os.path.join(WEB_DIR, asset))
    try:
        if os.path.commonpath((WEB_DIR, full)) != WEB_DIR:
            return None
    except ValueError:
        return None
    if not os.path.isfile(full):
        return None
    return full
