#!/usr/bin/env python3
"""
Portfolio studio server.

Serves the portfolio folder and accepts image drops from the page itself.
When you click or drop an image onto a dashed placeholder, the file is copied
into images/ and index.html is rewritten so the placeholder becomes a real
<figure>. The change is permanent and on disk — nothing lives only in the browser.

Run:  python studio.py         (then open http://127.0.0.1:8777/)
"""

import html
import http.server
import json
import os
import pathlib
import re
import shutil
import socketserver
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).parent.resolve()
PAGE = ROOT / "index.html"
IMAGES = ROOT / "images"
STATE = ROOT / ".studio"
ORIGINALS = STATE / "originals.json"

PORT = int(os.environ.get("STUDIO_PORT", "8777"))
MAX_BYTES = 40 * 1024 * 1024
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}


# --------------------------------------------------------------------------
# slot helpers
# --------------------------------------------------------------------------

def read_page() -> str:
    return PAGE.read_text(encoding="utf-8")


def write_page(text: str) -> None:
    tmp = PAGE.with_suffix(".html.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, PAGE)


def slot_bounds(page: str, slot: str):
    """Return (start, end) covering the whole <!--slot:x--> ... <!--/slot:x--> block."""
    open_tag = f"<!--slot:{slot}-->"
    close_tag = f"<!--/slot:{slot}-->"
    i = page.find(open_tag)
    if i == -1:
        return None
    j = page.find(close_tag, i)
    if j == -1:
        return None
    return i, j + len(close_tag)


def current_block(page: str, slot: str):
    b = slot_bounds(page, slot)
    if not b:
        return None
    start, end = b
    inner_start = start + len(f"<!--slot:{slot}-->")
    inner_end = end - len(f"<!--/slot:{slot}-->")
    return page[inner_start:inner_end]


def caption_of(block: str) -> str:
    m = re.search(r'data-caption="([^"]*)"', block)
    return html.unescape(m.group(1)) if m else "Image"


def load_originals() -> dict:
    if ORIGINALS.exists():
        try:
            return json.loads(ORIGINALS.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_originals(d: dict) -> None:
    STATE.mkdir(exist_ok=True)
    ORIGINALS.write_text(json.dumps(d, indent=2), encoding="utf-8")


def figure_markup(slot: str, caption: str, rel_src: str) -> str:
    cap_attr = html.escape(caption, quote=True)
    cap_text = html.escape(caption, quote=False)
    return (
        f'<figure class="fig" data-slot="{slot}" data-caption="{cap_attr}">'
        f'<img src="{rel_src}" alt="{cap_attr}" loading="lazy">'
        f"<figcaption>{cap_text}</figcaption>"
        f"</figure>"
    )


def fill_slot(slot: str, rel_src: str) -> str:
    page = read_page()
    bounds = slot_bounds(page, slot)
    if not bounds:
        raise KeyError(f"unknown slot: {slot}")
    start, end = bounds
    block = current_block(page, slot)
    caption = caption_of(block)

    originals = load_originals()
    if slot not in originals:
        originals[slot] = block
        save_originals(originals)

    new_block = (
        f"<!--slot:{slot}-->" + figure_markup(slot, caption, rel_src) + f"<!--/slot:{slot}-->"
    )
    write_page(page[:start] + new_block + page[end:])
    return caption


def revert_slot(slot: str) -> None:
    originals = load_originals()
    if slot not in originals:
        raise KeyError(f"no saved placeholder for: {slot}")
    page = read_page()
    bounds = slot_bounds(page, slot)
    if not bounds:
        raise KeyError(f"unknown slot: {slot}")
    start, end = bounds
    new_block = f"<!--slot:{slot}-->" + originals[slot] + f"<!--/slot:{slot}-->"
    write_page(page[:start] + new_block + page[end:])
    for f in IMAGES.glob(f"{slot}.*"):
        f.unlink(missing_ok=True)


def known_slots() -> set:
    return set(re.findall(r"<!--slot:([a-z0-9-]+)-->", read_page()))


# --------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # never cache the page while editing it
        if self.path.endswith(".html"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if urllib.parse.urlparse(self.path).path == "/api/ping":
            return self._json(200, {"studio": True, "slots": sorted(known_slots())})
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/upload":
            return self.handle_upload(params)
        if parsed.path == "/api/revert":
            return self.handle_revert(params)
        self._json(404, {"error": "no such endpoint"})

    def handle_upload(self, params):
        slot = (params.get("slot") or [""])[0]
        name = (params.get("name") or [""])[0]

        if not re.fullmatch(r"[a-z0-9-]+", slot or ""):
            return self._json(400, {"error": "bad slot id"})
        if slot not in known_slots():
            return self._json(404, {"error": f"slot '{slot}' is not in index.html"})

        ext = pathlib.Path(name).suffix.lower()
        if ext not in ALLOWED_EXT:
            return self._json(
                400, {"error": f"{ext or 'that file type'} not allowed — use PNG, JPG, WEBP, GIF or AVIF"}
            )

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._json(400, {"error": "empty upload"})
        if length > MAX_BYTES:
            return self._json(413, {"error": f"file is over {MAX_BYTES // 1024 // 1024}MB"})

        data = self.rfile.read(length)

        IMAGES.mkdir(exist_ok=True)
        for old in IMAGES.glob(f"{slot}.*"):
            old.unlink(missing_ok=True)
        dest = IMAGES / f"{slot}{ext}"
        dest.write_bytes(data)

        try:
            caption = fill_slot(slot, f"images/{dest.name}")
        except KeyError as e:
            return self._json(404, {"error": str(e)})

        print(f"  + {slot}  <-  {name}  ({len(data) // 1024} KB)")
        return self._json(200, {"ok": True, "slot": slot, "src": f"images/{dest.name}", "caption": caption})

    def handle_revert(self, params):
        slot = (params.get("slot") or [""])[0]
        if not re.fullmatch(r"[a-z0-9-]+", slot or ""):
            return self._json(400, {"error": "bad slot id"})
        try:
            revert_slot(slot)
        except KeyError as e:
            return self._json(404, {"error": str(e)})
        print(f"  - {slot}  reverted to placeholder")
        return self._json(200, {"ok": True, "slot": slot})


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    if not PAGE.exists():
        sys.exit(f"index.html not found in {ROOT}")
    IMAGES.mkdir(exist_ok=True)
    slots = known_slots()
    filled = len(re.findall(r'<figure class="fig" data-slot=', read_page()))
    print()
    print("  portfolio studio")
    print(f"  {ROOT}")
    print(f"  {len(slots)} image slots · {filled} filled by studio")
    print()
    print(f"  open  ->  http://127.0.0.1:{PORT}/")
    print("  drop an image on any dashed box, or click it to browse")
    print("  ctrl+c to stop")
    print()
    with Server(("127.0.0.1", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped\n")


if __name__ == "__main__":
    main()
