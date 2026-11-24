"""Screening: nur die ersten 300 KB jeder RAF per HTTP-Range lesen und die Fuji-Einstellungen auslesen."""
import sys, re, io, os, csv, struct, tempfile, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
from fuji_exif import read_makernote, FILM_MODE, ONOFF, GRAIN_SIZE, TONE
from PIL import Image
UA = {"User-Agent": "Mozilla/5.0 (compatible; sample-image-research)"}
cams = {"x_t3": "x_t3", "x_t4": "x_t4", "x_t5": "x_t5", "x_h2": "x_h2", "x_h2s": "x_h2s", "x_s10": "x_s10", "x_pro3": "x_pro3", "x100v": "x100v", "x_h1": "x_h1", "x_t30": "x_t30"}
urls = []
for cam in cams:
    html = open(f"/tmp/fujisim_pages/pb_{cam}.html", errors="ignore").read()
    for u in sorted(set(re.findall(r'https://[^"\']+?\.raf', html, flags=re.I))):
        urls.append((cam, u))
print(len(urls), "RAF-URLs", flush=True)

def head(u, n=300_000):
    import subprocess
    r = subprocess.run(["curl", "-sL", "-m", "60", "-A", UA["User-Agent"], "-r", f"0-{n-1}", "-D", "-", "-o", "-", u],
                       capture_output=True)
    sep = r.stdout.rfind(b"\r\n\r\n")
    hdr, body = r.stdout[:sep].decode("latin1"), r.stdout[sep + 4:]
    m = re.findall(r"content-range: bytes [^/]*/(\d+)", hdr, flags=re.I)
    return body, (m[-1] if m else "0")


def one(item):
    cam, u = item
    try:
        data, total = head(u)
        off = struct.unpack(">I", data[84:88])[0]
        jpg = data[off:]
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as t: t.write(jpg); path = t.name
        im = Image.open(path); ex = im.getexif().get_ifd(0x8769); mn = read_makernote(path); os.unlink(path)
        g = lambda k, m=None: (m.get(mn.get(k), mn.get(k)) if m else mn.get(k))
        return dict(cam=cam, url=u, mb=round(int(total or 0) / 1e6, 1), iso=ex.get(0x8827), film=g(0x1401, FILM_MODE), dr=g(0x1403),
                    hi=g(0x1041, TONE), sh=g(0x1040, TONE), color=g(0x1003), sharp=g(0x1001), grain=g(0x1047, ONOFF), gsize=g(0x104c, GRAIN_SIZE),
                    cce=g(0x1048, ONOFF), blue=g(0x104e, ONOFF), t100f=g(0x100f), nr=g(0x100e), wb=g(0x1002), tags=sorted(hex(k) for k in mn))
    except Exception as e:
        return dict(cam=cam, url=u, err=str(e)[:60])

with ThreadPoolExecutor(10) as ex:
    rows = list(ex.map(one, urls))
import json; json.dump(rows, open("/Users/leonkreutzer/Downloads/fujisim/calibration/screen.json", "w"))
ok = [r for r in rows if "err" not in r]; print(len(ok), "gelesen,", len(rows) - len(ok), "Fehler", flush=True)
