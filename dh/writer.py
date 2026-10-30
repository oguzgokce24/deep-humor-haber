"""Haberin görsel ve açıklama metnini yazar.

Haber sitelerinden haberin tam metni okunur ve Claude API'ye verilir. Claude, metni
bağlamlı kısa bir haber kartı olarak KENDİ CÜMLELERİYLE yeniden yazar. Doğrudan alıntılar
yalnızca kaynakta geçen sözlerden alınır.

ANTHROPIC_API_KEY yoksa ya da bir hata olursa, başlık + özet cümlesinden basit bir metin kurulur.
"""
from __future__ import annotations

import html
import json
import os
import re

import requests

UA = "Mozilla/5.0 (compatible; DeepHumorHaberBot/1.0)"
API_URL = "https://api.anthropic.com/v1/messages"

KATEGORILER = ["TÜRKİYE", "DÜNYA", "EKONOMİ", "SPOR"]

SYSTEM = """Sen Türkçe bir haber sayfasının editörüsün. Sana bir haberin birkaç kaynaktaki metnini
vereceğim. Bu habere, sosyal medyada paylaşılacak bir görselin üzerine yazılacak kısa ve BAĞLAMLI bir
metin yazacaksın. Okuyan kişi başka hiçbir yere bakmadan ne olduğunu, kimin ne dediğini ve neden
önemli olduğunu anlamalı.

Şu üç kalıptan habere en uygun olanı seç:

A) ALINTI (biri önemli bir açıklama yaptıysa):
**Unvan Ad Soyad:**

“Doğrudan alıntı, birinci kısım.

Gerekirse ikinci kısım.”

B) MADDELİ (karar, düzenleme, rakam, olay):
**Ne olduğunu anlatan tek cümle.**

— Bağlam maddesi (rakam, önceki durum, neden)
— Bağlam maddesi (kimi etkiliyor, ne zaman)
— Bağlam maddesi (isteğe bağlı)

C) KISA (tek bir net bilgi):
**Ana bilgi** rakam veya ayrıntı, **devamı.**

Kurallar:
- Yalnızca verilen kaynak metinlerdeki bilgileri kullan. Tahmin, yorum, abartı, duygusal sıfat ekleme.
  Kaynaklarda çelişen bilgi varsa ortak olanı yaz.
- Alıntılar dışındaki her şeyi KENDİ CÜMLELERİNLE yaz; kaynaktan cümle kopyalama.
- Alıntılar yalnızca kaynakta tırnak içinde geçen sözlerden, kelimesi kelimesine alınır; araya "(...)" koyarak
  kısaltabilirsin. Tırnak için “ ” kullan.
- Kişileri ilk geçtiği yerde unvanıyla yaz (ör. "ABD Türkiye Büyükelçisi Tom Barrack").
- Toplam en fazla 60 kelime. Kısa, net, akıcı Türkçe.
- **kalın** işaretini ana cümle / konuşanın adı / en kritik ifade için kullan; rakamlar normal kalabilir.
- Paragrafları boş satırla ayır. Madde satırları "— " ile başlar ve aralarında boş satır olmaz.
- Emoji, hashtag, kaynak/site adı, "son dakika" ifadesi YAZMA.
- Haber şiddet ya da ölüm içeriyorsa ayrıntıya girmeden, saygılı ve olgusal yaz.

Yanıtı YALNIZCA şu JSON biçiminde ver:
{"kategori": "TÜRKİYE" | "DÜNYA" | "EKONOMİ" | "SPOR", "metin": "..."}"""


def _article_text(url: str, limit: int = 3500) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        r.encoding = r.apparent_encoding or r.encoding
        doc = re.sub(r"(?is)<(script|style|noscript|figure|aside|nav|footer|header)[^>]*>.*?</\1>", " ", r.text)
        paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", doc)
        out = []
        for p in paras:
            t = html.unescape(re.sub(r"<[^>]+>", " ", p))
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) > 40 and not re.search(r"(?i)çerez|cookie|abone ol|tüm hakları|kvkk", t):
                out.append(t)
        return "\n".join(out)[:limit]
    except Exception:
        return ""


def gather_sources(cluster, max_sources: int = 3) -> str:
    """Önce ajans/kamu kaynakları olmak üzere birkaç farklı medya grubunun haber metnini toplar."""
    parts, groups = [], set()
    for it in sorted(cluster.items, key=lambda i: (not i.anchor,)):
        if it.group in groups or len(parts) >= max_sources:
            continue
        body = _article_text(it.link) or it.summary
        if body:
            parts.append(f"### {it.title}\n{body}")
            groups.add(it.group)
    return "\n\n".join(parts)


def _call_claude(source_text: str, model: str, key: str) -> dict:
    r = requests.post(API_URL, timeout=60, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 700, "system": SYSTEM,
              "messages": [{"role": "user", "content": f"Kaynak metinler:\n\n{source_text}"}]})
    js = r.json()
    if "error" in js:
        raise RuntimeError(js["error"].get("message"))
    raw = "".join(b.get("text", "") for b in js.get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0) if m else raw)
    text = (data.get("metin") or "").strip()
    if not text or len(text.split()) > 90:
        raise ValueError("metin boş ya da çok uzun")
    cat = (data.get("kategori") or "").strip().upper().replace("I", "I")
    return {"text": text, "category": cat if cat in KATEGORILER else None, "mode": "claude"}


def fallback(cluster) -> dict:
    lead = cluster.lead()
    text = f"**{lead.title.rstrip('.')}.**"
    s = re.sub(r"\s+", " ", lead.summary or "").strip()
    m = re.match(r"(.{30,240}?[.!?])(\s|$)", s)
    if m and m.group(1).lower()[:30] != lead.title.lower()[:30]:
        text += "\n\n" + m.group(1)
    return {"text": text, "category": None, "mode": "yedek"}


def write(cluster, model: str, log=print) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log("  (ANTHROPIC_API_KEY yok; basit metin kullanılıyor)")
        return fallback(cluster)
    try:
        src = gather_sources(cluster)
        return _call_claude(src, model, key)
    except Exception as e:
        log(f"  ! Metin yazımı başarısız ({e.__class__.__name__}: {str(e)[:80]}); basit metin kullanılıyor")
        return fallback(cluster)


def plain(markup: str) -> str:
    """Açıklama için **işaretleri** kaldırılmış düz metin."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", markup, flags=re.S).replace("**", "").strip()
