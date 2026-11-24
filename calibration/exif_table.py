import sys, io
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim"); sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
import rawpy
from PIL import Image
from fuji_exif import read_makernote, describe
D = "/Users/leonkreutzer/Downloads/fujisim/refs/xt2/fujifilm_x_t2_%02d.raf"
fit = {1:1.12,2:1.11,3:1.14,4:0.26,5:0.11,6:0.07,7:0.15,8:0.11,9:1.06,10:1.15,11:1.11,12:1.12,13:1.12}
print("RAF fitEV  ISO  t(s)     f     compEV  DRmode DRset  DRdev  AutoDR? | Tags 0x1400.. (DR) | Filmmode raw")
for n in range(1, 14):
    with rawpy.imread(D % n) as raw: t = raw.extract_thumb()
    open("/tmp/_emb.jpg", "wb").write(t.data)
    im = Image.open("/tmp/_emb.jpg"); ex = im.getexif().get_ifd(0x8769); mn = read_makernote("/tmp/_emb.jpg")
    print(f"{n:02d}  {fit[n]:+.2f} {ex.get(0x8827,'?'):>5} 1/{round(1/ex[0x829a]) if ex.get(0x829a) else '?':<5} {ex.get(0x829d)!s:5} {ex.get(0x9204)!s:6} {mn.get(0x1400)!s:6} {mn.get(0x1402)!s:6} {mn.get(0x1403)!s:6} {mn.get(0x140b)!s:6} | film={hex(mn.get(0x1401,0))} 0x1404={mn.get(0x1404)} 0x1405={mn.get(0x1405)}")
