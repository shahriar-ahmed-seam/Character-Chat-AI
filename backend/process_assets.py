"""One-off: process raw assets into web-ready files placed under web/public/."""
import os
from PIL import Image

SRC = r"C:\Projects\Character-Chat-AI\assets"
WEB = r"C:\Projects\Character-Chat-AI\web\public"

os.makedirs(os.path.join(WEB, "avatars"), exist_ok=True)


def save_square_webp(src, dst, size=512):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((size, size), Image.LANCZOS)
    img.save(dst, "WEBP", quality=88, method=6)
    print("wrote", dst, os.path.getsize(dst) // 1024, "KB")


# Character portraits -> circular-ready square webp avatars.
for cid in ("elias", "luna", "sergeant_kane"):
    save_square_webp(os.path.join(SRC, f"{cid}.png"),
                     os.path.join(WEB, "avatars", f"{cid}.webp"))

# App icons (PNG, required by the PWA manifest).
icon = Image.open(os.path.join(SRC, "icon.png")).convert("RGBA")
for s in (192, 512):
    icon.resize((s, s), Image.LANCZOS).save(os.path.join(WEB, f"icon-{s}.png"))
    print("wrote", f"icon-{s}.png")

# Logo / wordmark -> width-capped webp.
logo = Image.open(os.path.join(SRC, "logo.png")).convert("RGBA")
lw = 600
lh = round(logo.size[1] * lw / logo.size[0])
logo.resize((lw, lh), Image.LANCZOS).save(os.path.join(WEB, "logo.webp"), "WEBP", quality=90, method=6)
print("wrote logo.webp", lw, "x", lh)
