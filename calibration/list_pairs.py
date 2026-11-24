import sys, json
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
from fuji_exif import describe, read_makernote
from PIL import Image
ref = "/Users/leonkreutzer/Downloads/fujisim/refs/xt2/fujifilm_x_t2_%02d.jpg"
for n in range(1, 14):
    p = ref % n
    d = describe(p)
    ex = Image.open(p).getexif().get_ifd(0x8769)
    print(f"{n:02d} film={d['film']!s:15} DR={d['dr']} hi={d['highlight']} sh={d['shadow']} color={d['color']} sharp={d['sharpness']} "
          f"wb={d['wb']} grain={d['grain']} | ISO={ex.get(0x8827)} t=1/{round(1/ex[0x829a]) if ex.get(0x829a) else '?'} f/{ex.get(0x829d)} ev={ex.get(0x9204)} | {Image.open(p).size}")
print("\nRoh-Tags Bild 1:", describe(ref % 1)["raw_tags"])
