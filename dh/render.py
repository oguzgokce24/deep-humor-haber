"""Deep Humor haber kartı (1080x1350).

Düzen: tam ekran fotoğraf + lacivert karartma, solda beyaz dikey şerit ve yuvarlak logo,
başlığın arkasında silik büyük tırnak, başlık normal yazımla, sağ altta küçük aralıklı yazı.

Kendi logonu kullanmak için assets/logo.png koy (kare, şeffaf ya da dolu). Yoksa "DH" monogramı çizilir.
Başka başlık yazı tipi için assets/fonts/Headline.ttf koy (ör. Rubik Bold).
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1350
ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONTS = ASSETS / "fonts"

# Şerit ve logo ölçüleri (referans düzene göre)
BAR_X, BAR_W = 34, 58
BAR_TOP, BAR_BOTTOM = 205, 1202
LOGO_C, LOGO_R = (94, 208), 58
TEXT_X, TEXT_R = 148, 1032


def font(name: str, size: int):
    custom = FONTS / "Headline.ttf"
    if name == "headline" and custom.exists():
        return ImageFont.truetype(str(custom), size)
    files = {"headline": "InterDisplay-ExtraBold.otf", "bold": "InterDisplay-Bold.otf",
             "semibold": "InterDisplay-SemiBold.otf", "medium": "InterDisplay-Medium.otf",
             "black": "Inter-Black.otf", "quote": "QuoteSerif.ttf"}
    return ImageFont.truetype(str(FONTS / files[name]), size)


def tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def hex2rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_photo(src) -> Image.Image | None:
    try:
        if isinstance(src, (str, Path)) and str(src).startswith("http"):
            r = requests.get(str(src), timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content))
        elif src:
            im = Image.open(src)
        else:
            return None
        return ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        return None


def _fallback_bg(navy) -> Image.Image:
    bg = Image.new("RGB", (W, H), tuple(int(c * 0.7) for c in navy))
    d = ImageDraw.Draw(bg)
    d.ellipse([W - 700, -300, W + 300, 600], fill=tuple(min(255, int(c * 1.6)) for c in navy))
    d.ellipse([-300, 500, 500, 1300], fill=tuple(int(c * 1.2) for c in navy))
    return bg.filter(ImageFilter.GaussianBlur(120))


def _grade(img: Image.Image, navy, start: int) -> Image.Image:
    """Fotoğrafa lacivert/mor ton + alttan koyulaşan karartma."""
    img = img.convert("RGBA")
    tint = Image.new("RGBA", (W, H), navy + (38,))
    img.alpha_composite(tint)
    mask = Image.new("L", (1, H), 0)
    for y in range(H):
        if y > start:
            t = min(1.0, (y - start) / (H - start - 120))
            mask.putpixel((0, y), int(250 * (t ** 1.1)))
    grad = Image.new("RGBA", (W, H), navy + (255,))
    grad.putalpha(mask.resize((W, H)))
    img.alpha_composite(grad)
    return img


def _wrap(text: str, f, maxw: int):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if cur and f.getlength(t) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def _fit(text: str, maxw: int):
    # Önce 2 satıra sığdırmayı dener (referans düzen), olmazsa 3, en son 4 satır
    for max_lines, sizes in ((2, range(44, 37, -2)), (3, range(42, 35, -2))):
        for size in sizes:
            f = font("headline", size)
            lines = _wrap(text, f, maxw)
            if len(lines) <= max_lines:
                return f, lines, size
    f = font("headline", 36)
    lines = _wrap(text, f, maxw)
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return f, lines, 36


def _quote_mark(layer: Image.Image, x: int, y: int, color):
    """Yuvarlak, kalın açılış tırnağı (“) — iki adet '6' biçimi."""
    d = ImageDraw.Draw(layer)
    for dx in (0, 185):
        cx, cy, r = x + dx + 62, y + 175, 62
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        # yukarı kıvrılan kuyruk
        R = 150
        d.arc([cx - r + 2, cy - R - 20, cx - r + 2 + 2 * R, cy + R - 20], 180, 262, fill=color, width=46)


def _logo(d: ImageDraw.ImageDraw, canvas: Image.Image, navy, brand, ring=(255, 255, 255), ink=(255, 255, 255)):
    cx, cy = LOGO_C
    d.ellipse([cx - LOGO_R, cy - LOGO_R, cx + LOGO_R, cy + LOGO_R], fill=ring)
    r = LOGO_R - 5
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=navy)
    logo = ASSETS / "logo.png"
    if logo.exists():
        lg = Image.open(logo).convert("RGBA")
        lg = ImageOps.fit(lg, (2 * r, 2 * r), Image.LANCZOS)
        m = Image.new("L", (2 * r, 2 * r), 0)
        ImageDraw.Draw(m).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
        lg.putalpha(Image.composite(lg.getchannel("A"), m, m))
        canvas.alpha_composite(lg, (cx - r, cy - r))
        return
    mono = brand.get("monogram", "DH")
    f = font("black", 44)
    d.text((cx + 2, cy + 3), mono, font=f, fill=(0, 0, 0, 50), anchor="mm")
    d.text((cx, cy), mono, font=f, fill=ink, anchor="mm")
    # küçük alt çizgi vurgusu
    w = f.getlength(mono)
    d.rounded_rectangle([cx - w / 2, cy + 25, cx + w / 2, cy + 30], 3, fill=ink + (200,))


def _icon_info(d, x, y, c):
    d.ellipse([x - 13, y - 13, x + 13, y + 13], outline=c, width=3)
    d.rectangle([x - 1.5, y - 2, x + 1.5, y + 7], fill=c)
    d.ellipse([x - 2, y - 8, x + 2, y - 4], fill=c)


def _icon_pin(d, x, y, c):
    # şerit 90° döndürüleceği için iğnenin ucu aşağı bakacak şekilde çizilir
    d.ellipse([x - 10, y - 14, x + 10, y + 6], outline=c, width=3)
    d.polygon([(x - 7, y + 2), (x + 7, y + 2), (x, y + 15)], fill=c)
    d.ellipse([x - 3, y - 7, x + 3, y - 1], fill=c)


def _side_labels(canvas: Image.Image, navy, brand_short: str, label: str):
    """Şeridin altındaki dikey yazılar: ⓘ MARKA  📍 ETİKET (aşağıdan yukarı okunur)."""
    fs = font("bold", 23)
    strip_len = int(22 + 26 + fs.getlength(tr_upper(brand_short)) + 26 + 32 + fs.getlength(tr_upper(label)) + 10)
    strip = Image.new("RGBA", (strip_len, BAR_W), (0, 0, 0, 0))
    d = ImageDraw.Draw(strip)
    cy = BAR_W // 2
    x = 22
    _icon_info(d, x, cy, navy)
    x += 26
    d.text((x, cy), tr_upper(brand_short), font=fs, fill=navy, anchor="lm")
    x += fs.getlength(tr_upper(brand_short)) + 26
    _icon_pin(d, x, cy, navy)
    x += 32
    d.text((x, cy), tr_upper(label), font=fs, fill=navy, anchor="lm")
    strip = strip.rotate(90, expand=True, resample=Image.BICUBIC)
    canvas.alpha_composite(strip, (BAR_X, BAR_BOTTOM - 22 - strip.height + 0))


def render_card(title: str, photo=None, *, sources=(), photo_credit=None, label="TÜRKİYE",
                brand=None, theme=None, when: datetime | None = None, out_path=None,
                footer: str | None = None) -> Image.Image:
    brand = brand or {"name": "DEEP HUMOR", "short": "DEEP HUMOR", "monogram": "DH"}
    theme = theme or {}
    navy = hex2rgb(theme.get("overlay", theme.get("navy", "#06322F")))   # karartma tonu
    accent = hex2rgb(theme.get("accent", "#2FD39B"))                       # logo + vurgu
    strip = hex2rgb(theme.get("strip", "#FFFFFF"))                         # sol şerit
    strip_txt = hex2rgb(theme.get("strip_text", theme.get("overlay", "#06322F")))
    txt = hex2rgb(theme.get("text", "#FFFFFF"))

    im = load_photo(photo) if photo is not None else None
    base = ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.4)) if im else _fallback_bg(navy)

    # Başlık ölçüsü
    f, lines, size = _fit(title.strip(), TEXT_R - TEXT_X)
    lh = int(size * 1.02)
    head_bottom = 1120
    head_top = head_bottom - lh * len(lines)

    canvas = _grade(base, navy, start=max(560, head_top - 420))
    d = ImageDraw.Draw(canvas)

    # Silik büyük tırnak
    q = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _quote_mark(q, 205, head_top - 140, accent + (55,))
    canvas.alpha_composite(q.filter(ImageFilter.GaussianBlur(2)))

    # Sol şerit + logo
    d.rounded_rectangle([BAR_X, BAR_TOP, BAR_X + BAR_W, BAR_BOTTOM], BAR_W // 2, fill=strip)
    _logo(d, canvas, accent, brand, ring=strip, ink=hex2rgb(theme.get("logo_text", "#FFFFFF")))
    _side_labels(canvas, strip_txt, brand.get("short", brand.get("name", "")), label)

    # Başlık üstünde kısa vurgu çizgisi
    d.rounded_rectangle([TEXT_X, head_top - 30, TEXT_X + 70, head_top - 22], 4, fill=accent)

    # Başlık (gölgeli)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    y = head_top
    for ln in lines:
        sd.text((TEXT_X + 2, y + 3), ln, font=f, fill=(0, 0, 20, 140))
        y += lh
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    y = head_top
    for ln in lines:
        d.text((TEXT_X, y), ln, font=f, fill=txt)
        y += lh

    # Sağ alt: teyit kaynakları (aralıklı küçük büyük harf)
    if footer is None:
        footer = ("TEYİT: " + " · ".join(sources[:3])) if sources else ""
        if photo_credit:
            footer += ("   |   " if footer else "") + f"FOTO: {photo_credit}"
    if footer:
        ff = font("medium", 19)
        s = tr_upper(footer)
        spacing = 2.2
        total = sum(ff.getlength(ch) + spacing for ch in s) - spacing
        x = TEXT_R - total
        for ch in s:
            d.text((x, 1250), ch, font=ff, fill=(235, 235, 245), anchor="ls")
            x += ff.getlength(ch) + spacing

    out = canvas.convert("RGB")
    if out_path:
        out.save(out_path, "JPEG", quality=92)
    return out
