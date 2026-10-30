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

SYSTEM = """Sen bağımsız bir Türkçe haber sayfasının sosyal medya editörüsün. Tarzın; Instagram ve X'te
takip edilen bağımsız haber sayfaları gibi: sade, doğrudan, insanların gündelik konuştuğu dilde.
Kurumsal ajans dili KULLANMA. Sana bir haberin birkaç kaynaktaki metnini vereceğim. Görselin üzerine ve
gönderi açıklamasına aynen yazılacak kısa ama BAĞLAMLI bir metin yazacaksın. Okuyan, başka yere bakmadan
ne olduğunu ve neden önemli olduğunu anlamalı.

Habere en uygun kalıbı seç:

A) ALINTI — kaynakta çarpıcı bir söz varsa HER ZAMAN bunu tercih et:
**Ad Soyad:**

“Sözün en çarpıcı kısmı.

Gerekirse ikinci kısmı.”

(Unvan gerekiyorsa kısa tut: "**CHP Lideri Özgür Özel:**", "**Gazeteci İsmail Saymaz:**")

B) MADDELİ — karar, zam, düzenleme, rakam:
**Olayı gündelik dille anlatan tek cümle.**

— Kısa bağlam (önceki durum / rakam)
— Kısa bağlam (kimi etkiliyor / ne zaman)

C) KISA — tek net bilgi:
**Olay tek cümlede,** önemli rakam ya da ayrıntıyla.

DİL:
- Kısa cümleler. Özne + yüklem. Bir cümlede tek bilgi.
- Bürokratik kalıplar YASAK: "koordinasyonunda", "kapsamında", "açıklamasında bulundu", "ifadelerini kullandı",
  "gerçekleştirildi", "hususunda", "nezdinde", "tarafından yapılan", "itibarıyla" ve benzerleri.
- "X yaptı" de, "X tarafından yapıldı" deme. Edilgen yerine etken çatı.
- Başlık gibi değil, birine anlatır gibi yaz. Ama argo, küfür, alay, ünlem yağmuru yok.
- Protokol ayrıntılarını (hangi toplantıda, hangi heyetle) atla; olayın özüne odaklan.

DOĞRULUK (değişmez):
- Yalnızca kaynak metinlerdeki bilgileri kullan. Uydurma, tahmin, kendi yorumun yok.
  Bir yorumu sadece birinin sözü olarak, tırnak içinde ve adıyla verebilirsin.
- Alıntılar yalnızca kaynakta tırnak içinde geçen sözlerden ve kelimesi kelimesine alınır; uzunsa "(...)" ile kısalt.
  Alıntının toplamı en fazla 40 kelime. Tırnak için “ ” kullan.
- Alıntı dışındaki her şeyi KENDİ CÜMLELERİNLE yaz; kaynaktan cümle kopyalama.
- Ölüm/şiddet haberlerinde ayrıntıya girmeden, saygılı yaz.

BİÇİM:
- Toplam en fazla 65 kelime.
- **kalın**: konuşanın adı, ana cümle ya da en kritik ifade. Rakamlar normal kalabilir.
- Paragrafları boş satırla ayır. Madde satırları "— " ile başlar, aralarında boş satır olmaz.
- Emoji, hashtag, site/kaynak adı, "son dakika" yazma.

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
    if not text or len(text.split()) > 95:
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
