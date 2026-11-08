"""Deep Humor haber kartı (1080x1350).

Düzen: tam ekran fotoğraf + lacivert karartma, solda beyaz dikey şerit ve yuvarlak logo,
başlığın arkasında silik büyük tırnak, başlık normal yazımla, sağ altta küçük aralıklı yazı.

Kendi logonu kullanmak için assets/logo.png koy (kare, şeffaf ya da dolu). Yoksa "DH" monogramı çizilir.
Başka başlık yazı tipi için assets/fonts/Headline.ttf koy (ör. Rubik Bold).
"""
from __future__ import annotations

import io
import re
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
        if isinstance(src, Image.Image):
            return src.convert("RGB")
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


# Gerçek fotoğraf olmayan görselleri (son dakika kartı, logo, varsayılan görsel) ayıklamak için
_BAD_URL = re.compile(r"(son-?dakika|sondakika|breaking|default|placeholder|no-?image|noimage|logo|"
                      r"generic|bos-?gorsel|haber-?gorseli|share-?image|og-?default|fallback)", re.I)


def photo_ok(im: Image.Image | None, url: str = "") -> tuple[bool, str]:
    """Fotoğraf şablona uygun mu? (uygun_mu, neden)"""
    if im is None:
        return False, "indirilemedi"
    if url and _BAD_URL.search(url.split("?")[0]):
        return False, "varsayılan/son dakika görseli"
    w, h = im.size
    if min(w, h) < 380:
        return False, "çok küçük"
    if w / h > 2.4 or h / w > 2.4:
        return False, "oranı uygun değil"
    # Düz renkli grafik / yazı kartı mı? Fotoğraflarda renk çeşitliliği yüksektir.
    small = im.resize((64, 64)).quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    used = len([c for c in small.getcolors(256) or [] if c[0] >= 2])
    if used < 90:
        return False, "fotoğraf değil (grafik/yazı kartı)"
    return True, ""


def pick_photo(candidates, log=print):
    """[(url, kaynak), ...] içinden şablona uygun ilk fotoğrafı döndürür: (Image, kaynak) ya da (None, None)."""
    seen = set()
    for url, src in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        im = load_photo(url)
        ok, why = photo_ok(im, url)
        if ok:
            return im, src
        log(f"  görsel atlandı ({src}: {why})")
    return None, None


def wikimedia_photo(person: str, log=print):
    """Tanınmış kişinin SERBEST LİSANSLI (Wikimedia Commons) fotoğrafı. (Image, künye) ya da (None, None)."""
    if not person:
        return None, None
    for lang in ("tr", "en"):
        try:
            r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", timeout=15,
                             headers={"User-Agent": "DeepHumorHaberBot/1.0 (haber otomasyonu)"},
                             params={"action": "query", "titles": person, "prop": "pageimages",
                                     "piprop": "original", "pilicense": "free", "redirects": 1, "format": "json"})
            pages = r.json().get("query", {}).get("pages", {})
            for pg in pages.values():
                url = pg.get("original", {}).get("source")
                if url and not url.lower().endswith((".svg", ".gif")):
                    im = load_photo(url)
                    ok, why = photo_ok(im, url)
                    if ok:
                        return im, "Wikimedia Commons"
        except Exception:
            continue
    log(f"  Wikimedia'da uygun fotoğraf yok: {person}")
    return None, None


def compose_photo(im: Image.Image, text_top: int) -> Image.Image:
    """Dikey (4:5) kadraja yerleştirir. Dikey/kareye yakın fotoğraflar doldurularak kırpılır;
    yatay fotoğraflar KESİLMEZ: bulanık arka plan üzerine tam genişlikte, metnin üstündeki alana oturtulur."""
    w, h = im.size
    if w / h <= 0.95:
        return ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.35))
    bg = ImageOps.fit(im, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.35)
    fw = W
    fh = int(h * fw / w)
    space = max(text_top - 60, fh)          # metnin üstünde kalan alan
    y = max(0, (space - fh) // 2)
    fg = im.resize((fw, fh), Image.LANCZOS)
    # kenarları yumuşak geçişle arka plana karışsın
    mask = Image.new("L", (fw, fh), 255)
    md = ImageDraw.Draw(mask)
    fade = min(70, fh // 6)
    for i in range(fade):
        a = int(255 * i / fade)
        md.line([(0, i), (fw, i)], fill=a)
        md.line([(0, fh - 1 - i), (fw, fh - 1 - i)], fill=a)
    bg.paste(fg, (0, y), mask)
    return bg


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


# ---------------------------------------------------------------- Çok paragraflı zengin metin
def _segments_md(line: str):
    """'**kalın** normal' -> [(kelime, kalın_mı), ...]"""
    out = []
    for i, part in enumerate(re.split(r"\*\*", line)):
        for w in part.split():
            out.append((w, i % 2 == 1))
    return out


def _layout_body(markup: str, maxw: int, max_h: int):
    paras = [p.strip("\n") for p in re.split(r"\n\s*\n", markup.strip()) if p.strip()]
    for size in range(60, 25, -2):
        fb, fr = font("headline", size), font("bold", size)   # tüm metin kalın, vurgular daha da kalın
        lh, gap = int(size * 1.2), int(size * 0.75)
        sp = fr.getlength(" ")
        rows, h = [], 0
        for pi, para in enumerate(paras):
            if pi:
                rows.append(None)  # paragraf boşluğu
                h += gap
            for src in para.split("\n"):
                cur, curw = [], 0
                for w, b in _segments_md(src):
                    ww = (fb if b else fr).getlength(w)
                    if cur and curw + sp + ww > maxw:
                        rows.append(cur); h += lh
                        cur, curw = [], 0
                    cur.append((w, b)); curw += (sp if len(cur) > 1 else 0) + ww
                if cur:
                    rows.append(cur); h += lh
        if h <= max_h or size <= 26:
            return {"rows": rows, "fb": fb, "fr": fr, "lh": lh, "gap": gap, "sp": sp, "height": h}


def fit_card_text(markup: str, maxw: int, max_h: int = 450, min_size: int = 46) -> str:
    """Görsele yalnızca ÖNEMLİ kısım konur: ilk paragraf (ana cümle / alıntı) ve sığarsa ilk madde.
    Yazı büyük ve okunur kalsın diye fazlası görsele girmez; tam metin açıklamada yer alır."""
    paras = [p.strip() for p in markup.strip().split("\n\n") if p.strip()]
    if not paras:
        return markup.strip()
    core = [paras[0]]
    # "**Ad Soyad:**" gibi çok kısa bir ilk paragrafsa alıntıyı da al
    if len(re.sub(r"[*“”\"]", "", paras[0]).split()) < 6 and len(paras) > 1:
        core.append(paras[1])
    rest = "\n".join(paras[len(core):]).split("\n")
    extra = rest[0].strip() if rest and rest[0].strip() else ""
    # Ek satır tek başına tam bir cümle olmalı: "**Ad Soyad:**" gibi devamı başka satırda olan etiketler alınmaz
    if not re.search(r"[.!?…][*”\"’')]*$", extra):
        extra = ""
    base = "\n\n".join(core)
    if extra:
        cand = base + "\n\n" + extra
        L = _layout_body(cand, maxw, max_h)
        if L["height"] <= max_h and L["fb"].size >= min_size:
            return cand
    return base


def _draw_layout(d, L, x0, y0, fill):
    y = y0
    for row in L["rows"]:
        if row is None:
            y += L["gap"]
            continue
        x = x0
        for w, b in row:
            f = L["fb"] if b else L["fr"]
            d.text((x + 2, y + 2), w, font=f, fill=(0, 0, 0))     # hafif gölge: fotoğraf üstünde okunurluk
            d.text((x, y), w, font=f, fill=fill)
            x += f.getlength(w) + L["sp"]
        y += L["lh"]


SCORE_H = 250


def _score_band(canvas: Image.Image, sc: dict, top: int, navy, accent, txt):
    """Maç sonucu bandı: üstte lig/hafta, iki satır takım + skor, altta goller. Logo kullanılmaz."""
    x0, x1 = TEXT_X - 18, TEXT_R
    panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle([x0, top, x1, top + SCORE_H], 22, fill=navy + (215,))
    pd.rounded_rectangle([x0, top, x0 + 10, top + SCORE_H], 5, fill=accent + (255,))
    canvas.alpha_composite(panel)
    d = ImageDraw.Draw(canvas)
    info = tr_upper(sc.get("info", ""))
    if info:
        d.text((x0 + 36, top + 22), info, font=font("bold", 22), fill=accent)
    fteam, fnum = font("headline", 50), font("headline", 72)
    rows = [(sc["home"], sc["home_score"]), (sc["away"], sc["away_score"])]
    hs, as_ = int(sc["home_score"]), int(sc["away_score"])
    for k, (team, num) in enumerate(rows):
        y = top + 58 + k * 74
        win = (k == 0 and hs > as_) or (k == 1 and as_ > hs)
        d.text((x0 + 36, y + 6), tr_upper(team), font=fteam, fill=txt if win or hs == as_ else (200, 214, 210))
        box = [x1 - 112, y - 2, x1 - 28, y + 70]
        d.rounded_rectangle(box, 12, fill=accent if win else (255, 255, 255))
        d.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2 + 2), str(num), font=fnum,
               fill=navy, anchor="mm")
    goals = sc.get("goals", "")
    if goals:
        d.text((x0 + 36, top + SCORE_H - 40), goals, font=font("medium", 22), fill=(220, 232, 228))


def render_card(title: str, photo=None, *, sources=(), photo_credit=None, label="TÜRKİYE",
                brand=None, theme=None, when: datetime | None = None, out_path=None,
                footer: str | None = None, body: str | None = None, score: dict | None = None) -> Image.Image:
    brand = brand or {"name": "DEEP HUMOR", "short": "DEEP HUMOR", "monogram": "DH"}
    theme = theme or {}
    navy = hex2rgb(theme.get("overlay", theme.get("navy", "#06322F")))   # karartma tonu
    accent = hex2rgb(theme.get("accent", "#2FD39B"))                       # logo + vurgu
    strip = hex2rgb(theme.get("strip", "#FFFFFF"))                         # sol şerit
    strip_txt = hex2rgb(theme.get("strip_text", theme.get("overlay", "#06322F")))
    txt = hex2rgb(theme.get("text", "#FFFFFF"))


    # Metin düzeni: body (çok paragraflı, **kalın** işaretli) varsa o, yoksa başlık
    text_h = 280 if score else 420          # skor bandı varsa görseldeki metin kısalır
    markup = fit_card_text(body, TEXT_R - TEXT_X, max_h=text_h) if body else f"**{title.strip()}**"
    layout = _layout_body(markup, TEXT_R - TEXT_X, max_h=text_h)
    head_bottom = 1180
    head_top = head_bottom - layout["height"]
    score_top = None
    if score:
        score_top = head_top - 60 - SCORE_H
        head_top_for_photo = score_top
    else:
        head_top_for_photo = head_top

    im = load_photo(photo) if photo is not None else None
    base = compose_photo(im, head_top_for_photo) if im else _fallback_bg(navy)

    canvas = _grade(base, navy, start=max(380, head_top_for_photo - 380))
    d = ImageDraw.Draw(canvas)

    # Silik büyük tırnak (yalnızca alıntı içeren metinlerde)
    if "“" in markup or '"' in markup:
        q = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        _quote_mark(q, 205, head_top - 110, accent + (50,))
        canvas.alpha_composite(q.filter(ImageFilter.GaussianBlur(2)))

    # Sol şerit + logo
    d.rounded_rectangle([BAR_X, BAR_TOP, BAR_X + BAR_W, BAR_BOTTOM], BAR_W // 2, fill=strip)
    _logo(d, canvas, accent, brand, ring=strip, ink=hex2rgb(theme.get("logo_text", "#FFFFFF")))
    _side_labels(canvas, strip_txt, brand.get("short", brand.get("name", "")), label)

    if score:
        _score_band(canvas, score, score_top, navy, accent, txt)

    # Metnin üstünde kısa vurgu çizgisi
    d.rounded_rectangle([TEXT_X, head_top - 30, TEXT_X + 70, head_top - 22], 4, fill=accent)

    # Metin (önce gölge, sonra yazı)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_layout(ImageDraw.Draw(sh), layout, TEXT_X + 2, head_top + 3, (0, 0, 20, 150))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    _draw_layout(d, layout, TEXT_X, head_top, txt)

    # Sağ alt yazı (varsayılan boş; teyit/fotoğraf bilgisi görselde gösterilmez)
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
        out.save(out_path, "JPEG", quality=95, subsampling=0, optimize=True)  # yazılar keskin kalsın
    return out
