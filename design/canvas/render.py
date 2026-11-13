# Renders the artboards gen.py writes into design/renders/*.png, at 2×, with
# headless Chrome — no window opens — and a throwaway profile, so nobody's own
# Chrome is touched. Each page is shot tall and the empty window ground under
# the strip is cut off, with nothing but the standard library (zlib), since
# this box has no image library. Run it after gen.py:
#     .venv/bin/python design/canvas/render.py
import json, os, struct, subprocess, sys, tempfile, time, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "renders")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH, TALL, SCALE = 484, 5200, 2
GROUND = (240, 240, 240)   # #f0f0f0, the window ground under the strip


def _chunks(data):
    at = 8
    while at < len(data):
        length, kind = struct.unpack(">I4s", data[at:at + 8])
        yield kind, data[at + 8:at + 8 + length]
        at += 12 + length


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def read_png(path):
    """(width, height, channels, rows) of an 8-bit RGB or RGBA PNG, rows unfiltered."""
    data = open(path, "rb").read()
    header, idat = None, b""
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
    width, height, depth, colour = header[:4]
    if depth != 8 or colour not in (2, 6):
        raise SystemExit(f"{path}: only 8-bit RGB or RGBA is read here (got depth {depth}, colour {colour}).")
    channels = 3 if colour == 2 else 4
    raw = zlib.decompress(idat)
    stride = width * channels
    rows, previous = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + left) & 255
            elif kind == 2:
                line[x] = (line[x] + up) & 255
            elif kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif kind == 4:
                line[x] = (line[x] + _paeth(left, up, corner)) & 255
        rows.append(bytes(line))
        previous = line
    return width, height, channels, rows


def write_png(path, width, channels, rows):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", width, len(rows), 8, 2 if channels == 3 else 6, 0, 0, 0)
    body = zlib.compress(b"".join(b"\x00" + row for row in rows), 9)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b""))


def trimmed(rows, channels, margin=12 * SCALE):
    """The rows down to the last one that is not all window ground, and a margin of ground under it."""
    ground = bytes(GROUND) if channels == 3 else bytes(GROUND) + b"\xff"
    last = 0
    for y, row in enumerate(rows):
        if row != ground * (len(row) // channels):
            last = y
    return rows[:min(len(rows), last + 1 + margin)]


def _shoot(page, shot, width=WIDTH, wait=90.0):
    """Headless Chrome writes the screenshot, but on macOS does not always exit after: wait for the
    file to appear and stop growing, then stop the process ourselves."""
    with tempfile.TemporaryDirectory() as profile:
        chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                                   "--disable-extensions", "--hide-scrollbars", f"--user-data-dir={profile}",
                                   f"--force-device-scale-factor={SCALE}", f"--window-size={width},{TALL}",
                                   "--timeout=6000", f"--screenshot={shot}", "file://" + page],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline, size = time.time() + wait, -1
            while time.time() < deadline:
                time.sleep(1.0)
                now = os.path.getsize(shot) if os.path.exists(shot) else -1
                if now > 0 and now == size:
                    return
                size = now
            raise SystemExit(f"Chrome wrote no screenshot of {page} in {wait:g} s.")
        finally:
            chrome.terminate()
            try:
                chrome.wait(10)
            except subprocess.TimeoutExpired:
                chrome.kill()


def render(name, width=WIDTH):
    page = os.path.join(HERE, f"{name}.dc.html")
    shot = os.path.join(tempfile.mkdtemp(), f"{name}.png")
    _shoot(page, shot, width)
    width, _, channels, rows = read_png(shot)
    kept = trimmed(rows, channels)
    target = os.path.join(OUT, f"{name}.png")
    write_png(target, width, channels, kept)
    return target, width, len(kept)


if __name__ == "__main__":
    artboards = json.load(open(os.path.join(HERE, "canvas.json")))["artboards"]
    widths = {a["file"][:-len(".dc.html")]: a.get("w", WIDTH) for a in artboards}
    for name in (sys.argv[1:] or list(widths)):
        target, width, height = render(name, widths.get(name, WIDTH))
        print(f"{os.path.relpath(target, os.path.join(HERE, '..', '..'))}  {width} × {height}")
