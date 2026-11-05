"""Deep Humor Haber otomasyonu.

Her çalıştırmada:
  1) Haber kaynaklarını tarar, çok kaynaklı doğrulanan yeni haberi bulur
  2) Görselini hazırlar ve doğrudan Facebook sayfasında paylaşır

Kullanım:
  python main.py            # normal çalışma (GitHub Actions)
  python main.py --dry-run  # Facebook'a göndermeden dene; görseller out/ klasörüne
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from dh.collect import fetch_all, og_image
from dh.render import render_card, pick_photo
from dh import writer
from dh.verify import cluster, verified, similarity, story_tokens, is_duplicate_title
from dh.verify import tokens as vtokens, _strong as vstrong
from dh.channels import FacebookPage

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "state.json"
OUT = ROOT / "out"
TR = timezone(timedelta(hours=3))

KATEGORI = {
    "EKONOMİ": ["faiz", "dolar", "enflas", "borsa", "merkez banka", "asgari ücret", "euro", "altın", "zam"],
    "SPOR": ["galatasaray", "fenerbahçe", "beşiktaş", "trabzonspor", "milli takım", "maç", "gol", "transfer"],
    "DÜNYA": ["abd", "rusya", "ukrayna", "israil", "gazze", "iran", "avrupa", "nato", "bm "],
    "DEPREM": ["deprem", "afad", "büyüklüğünde"],
}


def log(*a):
    print(*a, flush=True)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"seen": [], "posted": []}


def save_state(st):
    now = datetime.now(timezone.utc)
    st["seen"] = [s for s in st["seen"] if now - datetime.fromisoformat(s["at"]) < timedelta(hours=36)]
    st["posted"] = st["posted"][-200:]
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def label_for(c) -> str:
    low = " " + c.lead().title.lower() + " "
    # Görseldeki dikey şeritte yazan etiket (ör. TÜRKİYE, DÜNYA, EKONOMİ, SPOR)
    for k, words in KATEGORI.items():
        if any(w in low for w in words):
            return "TÜRKİYE" if k == "DEPREM" else k
    return "TÜRKİYE"


def first_sentence(s: str, limit=260) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    m = re.match(r"(.{40,%d}?[.!?])(\s|$)" % limit, s)
    return (m.group(1) if m else s[:limit]).strip()


def build_caption(c, title, credit, brand) -> str:
    lead = c.lead()
    lines = [f"📰 {title}"]
    summ = first_sentence(lead.summary)
    if summ and summ.lower()[:40] != title.lower()[:40]:
        lines += ["", summ]
    lines += ["", brand.get("hashtags", "")]
    return "\n".join(lines).strip()


GENERIC_IMAGES: set[str] = set()

# ---------------------------------------------------------------- Haber seçimi
# Bağımsız haber sayfası tarzı: alıntılı / insan hikâyesi / gündemi sarsan haberler öne,
# protokol ve tören haberleri geriye.
PROTOKOL = ["forum", "zirve", "konsey", "tören", "törenle", "resepsiyon", "tebrik", "kutladı", "kutlama",
            "paylaşımı", "mesajı", "anma", "ziyaret etti", "kabul etti", "görüştü", "bir araya geldi",
            "katıldı", "toplantısı", "çalıştayı", "işbirliği", "imza töreni"]
CEKICI = ["istifa", "tepki", "itiraf", "sert", "olay", "ilk kez", "yüzde", "zam", "maaş", "fiyat",
          "tutuklandı", "gözaltı", "karar", "rekor", "açıkladı", "çağrı", "uyardı", "iddia",
          # asayiş / olay / magazin-gündem
          "öldürdü", "öldürüldü", "cinayet", "silahlı", "bıçak", "saldırı", "patlama", "yangın", "kaza",
          "deprem", "kayıp", "tahliye", "suç duyurusu", "iftira", "dava", "boşan", "skandal", "ifşa",
          "ünlü", "oyuncu", "şarkıcı", "fenomen", "gazeteci"]


def _tr_low(t: str) -> str:
    return t.replace("I", "ı").replace("İ", "i").lower()


def excluded(c, words) -> bool:
    """Başlık/özetlerinde hariç tutulan bir ifade geçen haber (ör. basketbol) paylaşılmaz."""
    if not words:
        return False
    text = " " + _tr_low(" ".join(i.title + " " + (i.summary or "") for i in c.items)) + " "
    for w in words:
        if re.search(r"(?<![a-zçğıöşü0-9])" + re.escape(_tr_low(str(w))), text):
            return True
    return False


SPOR = ["maç", "gol", "lig", "transfer", "teknik direktör", "hakem", "penaltı", "şampiyonlar ligi",
        "avrupa ligi", "konferans ligi", "süper lig", "milli takım", "galatasaray", "fenerbahçe", "beşiktaş",
        "trabzonspor", "derbi", "futbol", "uefa", "fifa", "skor", "deplasman"]


def is_sport(text: str) -> bool:
    t = " " + _tr_low(text) + " "
    return sum(1 for w in SPOR if re.search(r"(?<![a-zçğıöşü])" + re.escape(w), t)) >= 1


def interest_score(c) -> float:
    t = " " + " ".join(i.title.lower() for i in c.items[:6]) + " "
    lead = c.lead().title
    score = min(len(c.groups), 8)                       # haberin büyüklüğü (en fazla 8 puan)
    if re.search(r"^[^:]{3,60}:\s", lead) or "\"" in lead or "“" in lead or "'" in lead[:1]:
        score += 2.5                                    # "Kişi: söz" biçimi / doğrudan alıntı
    if any(i.independent for i in c.items):
        score += 1.5                                    # bağımsız sitelerde de yer alıyor
    score += 0.5 * sum(1 for w in CEKICI if w in t)
    score -= 3 * sum(1 for w in PROTOKOL if w in t)
    if c.latest:
        age_h = (datetime.now(timezone.utc) - c.latest).total_seconds() / 3600
        score -= age_h                                  # eskidikçe geriye
    return score


# ---------------------------------------------------------------- Yeni haber bulma
def find_new(cfg, st):
    v = cfg["verify"]
    log("Kaynaklar taranıyor…")
    items = fetch_all(cfg["sources"], v["max_age_hours"], log)
    # Aynı görsel birden fazla FARKLI habere eklenmişse bu bir "son dakika" kartı / varsayılan görseldir
    from collections import defaultdict
    by_img = defaultdict(set)
    for it in items:
        if it.image:
            by_img[it.image.split("?")[0]].add(it.title.strip().lower()[:40])
    GENERIC_IMAGES.clear()
    GENERIC_IMAGES.update(u for u, titles in by_img.items() if len(titles) >= 2)
    if GENERIC_IMAGES:
        log(f"  {len(GENERIC_IMAGES)} ortak/varsayılan görsel ayıklandı")
    clusters = cluster(items, v["similarity"])
    ok = verified(clusters, v["min_groups"], v["require_anchor"], v.get("fast_lane_minutes", 0))
    log(f"{len(items)} haber, {len(clusters)} küme, {len(ok)} doğrulanmış küme")
    excl = [w.strip() for w in cfg.get("exclude", []) if str(w).strip()]
    # Konu çeşitliliği: son paylaşımların konuları
    last = st.get("posted", [])[-3:]
    last_toks = [{t for t in vtokens(p["title"] + " " + p.get("metin", "")[:200]) if vstrong(t)} for p in last]
    last_sport = sum(1 for p in last[-2:] if is_sport(p["title"] + " " + p.get("metin", "")))
    # Son 36 saatte paylaşılanların başlık + metinlerinden ayırt edici kelimeler (tekrar kontrolü için)
    now = datetime.now(timezone.utc)
    recent_posts = [{t for t in vtokens(p["title"] + " " + p.get("metin", "")) if vstrong(t)}
                    for p in st.get("posted", [])
                    if now - datetime.fromisoformat(p["at"]) < timedelta(hours=36)]
    fresh = []
    def score(c):
        sc = interest_score(c)
        if is_sport(" ".join(i.title for i in c.items[:4])):
            sc -= 3 * last_sport                    # son paylaşımlar sporsa sporu geriye at
        return sc

    for c in sorted(ok, key=score, reverse=True):
        if excluded(c, excl):
            continue
        # Aynı konunun devamı (ör. aynı maçın ikinci haberi) son 3 paylaşımdan biriyle 2+ özel isim paylaşıyorsa atla
        lt = {t for t in vtokens(c.lead().title) if vstrong(t)}
        sport_now = is_sport(c.lead().title)
        if any(len(lt & pt) >= 2 or (sport_now and lt & pt and is_sport(p["title"]))
               for pt, p in zip(last_toks, last)):
            continue
        fp = c.fingerprint
        titles = [i.title for i in c.items]
        if any(similarity(fp, set(s["fp"])) >= 0.5 or is_duplicate_title(titles, set(s.get("tok", [])))
               for s in st["seen"]) or any(is_duplicate_title(titles, pt) for pt in recent_posts):
            continue
        fresh.append(c)
    return fresh


def recently_posted(st, minutes: int) -> bool:
    if not st["posted"]:
        return False
    last = datetime.fromisoformat(st["posted"][-1]["at"])
    return datetime.now(timezone.utc) - last < timedelta(minutes=minutes)


def load_local_keys():
    """Bilgisayarda çalışırken anahtarları klasördeki anahtarlar.txt dosyasından okur (ANAHTAR=değer)."""
    f = ROOT / "anahtarlar.txt"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip())


def main():
    dry = "--dry-run" in sys.argv
    load_local_keys()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    pub = cfg["publish"]
    st = load_state()
    st.setdefault("seen", []); st.setdefault("posted", [])
    OUT.mkdir(exist_ok=True)

    fb = None
    if not dry:
        page_id = os.environ.get("FB_PAGE_ID") or str(pub.get("page_id", ""))
        if not page_id or not os.environ.get("FB_PAGE_TOKEN"):
            sys.exit("Eksik ayar: FB_PAGE_TOKEN gizli anahtarı (ve config.yaml'da page_id) gerekli. README'ye bak.")
        fb = FacebookPage(page_id, os.environ["FB_PAGE_TOKEN"], pub["graph_version"])
        if recently_posted(st, pub["min_gap_minutes"]):
            log(f"Son paylaşımın üzerinden {pub['min_gap_minutes']} dk geçmedi, bu tur atlanıyor.")
            return

    sent = 0
    for c in find_new(cfg, st):
        if sent >= pub["max_per_run"]:
            break
        lead = c.lead()
        # Görsel adayları: önce RSS görselleri, sonra haber sayfalarının paylaşım görselleri.
        # Son dakika kartı / logo / küçük ya da grafik görseller elenir; uygun yoksa düz zemin kullanılır.
        cands = [(i.image, i.source) for i in sorted(c.usable, key=lambda i: not i.anchor) if i.image]
        cands += [(og_image(i.link), i.source) for i in sorted(c.usable, key=lambda i: not i.anchor)[:3]]
        cands = [(u, src) for u, src in cands if u and u.split("?")[0] not in GENERIC_IMAGES]
        img, credit = pick_photo(cands, log)
        title = lead.title
        pid = hashlib.sha1(" ".join(sorted(c.fingerprint)).encode()).hexdigest()[:10]
        path = OUT / f"{pid}.jpg"
        w = writer.write(c, cfg.get("writer", {}).get("model", "claude-haiku-5-5"), log)
        if w is None:
            fails = st.setdefault("fails", {})
            # Küme büyüdükçe parmak izi değişir; denemeleri haberin ilk bağlantısına göre say
            fkey = hashlib.sha1(min(i.link for i in c.items).encode()).hexdigest()[:10]
            fails[fkey] = fails.get(fkey, 0) + 1
            if len(fails) > 300:
                st["fails"] = fails = dict(list(fails.items())[-150:])
            if fails[fkey] >= 3:   # 3 turda da yazılamadıysa bu haberden vazgeç
                st["seen"].append({"fp": sorted(c.fingerprint), "tok": sorted(story_tokens(c))[:80],
                                   "at": datetime.now(timezone.utc).isoformat()})
                fails.pop(fkey, None)
            log("  Metin yazılamadı; bu haber bu tur paylaşılmıyor.")
            continue
        label = w["category"] or label_for(c)
        render_card(title, img, body=w["text"], label=label,
                    brand=cfg["brand"], theme=cfg["theme"], out_path=path)
        caption = writer.plain(w["text"])
        tags = cfg["brand"].get("hashtags", "").strip()
        if tags:
            caption += "\n\n" + tags
        links = "\n".join(f"  {i.source}: {i.link}" for i in c.items[:6])
        now = datetime.now(timezone.utc).isoformat()
        # Aynı haber bir daha denenmesin (paylaşım hata verse bile)
        st["seen"].append({"fp": sorted(c.fingerprint), "tok": sorted(story_tokens(c, caption))[:80], "at": now})

        if dry:
            log(f"\n[{pid}] {path.name}\n{caption}\nKaynaklar:\n{links}\n")
            sent += 1
            continue
        try:
            post_id = fb.post_photo(path.read_bytes(), caption)
        except Exception as e:
            log(f"HATA paylaşım: {e}")
            continue
        st["posted"].append({"id": pid, "post_id": post_id, "title": title, "at": now,
                             "yazim": w.get("mode"), "metin": caption,
                             "sources": [f"{i.source}: {i.link}" for i in c.items[:6]]})
        log(f"Paylaşıldı: {title} -> {post_id}\nKaynaklar:\n{links}")
        sent += 1

    if not sent:
        log("Yeni doğrulanmış haber yok.")
    if not dry:
        save_state(st)


if __name__ == "__main__":
    main()
