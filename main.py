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
from dh.render import render_card
from dh import writer
from dh.verify import cluster, verified, similarity
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


# ---------------------------------------------------------------- Yeni haber bulma
def find_new(cfg, st):
    v = cfg["verify"]
    log("Kaynaklar taranıyor…")
    items = fetch_all(cfg["sources"], v["max_age_hours"], log)
    clusters = cluster(items, v["similarity"])
    ok = verified(clusters, v["min_groups"], v["require_anchor"])
    log(f"{len(items)} haber, {len(clusters)} küme, {len(ok)} doğrulanmış küme")
    fresh = []
    for c in ok:
        fp = c.fingerprint
        if any(similarity(fp, set(s["fp"])) >= 0.5 for s in st["seen"]):
            continue
        fresh.append(c)
    return fresh


def recently_posted(st, minutes: int) -> bool:
    if not st["posted"]:
        return False
    last = datetime.fromisoformat(st["posted"][-1]["at"])
    return datetime.now(timezone.utc) - last < timedelta(minutes=minutes)


def main():
    dry = "--dry-run" in sys.argv
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
        img, credit = c.best_image()
        if not img:
            for it in sorted(c.items, key=lambda i: not i.anchor)[:3]:
                img = og_image(it.link)
                if img:
                    credit = it.source
                    break
        title = lead.title
        pid = hashlib.sha1(" ".join(sorted(c.fingerprint)).encode()).hexdigest()[:10]
        path = OUT / f"{pid}.jpg"
        w = writer.write(c, cfg.get("writer", {}).get("model", "claude-haiku-5-5"), log)
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
        st["seen"].append({"fp": sorted(c.fingerprint), "at": now})

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
