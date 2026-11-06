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

Ardından mutlaka 1–2 cümlelik bağlam ekle (neden, ne zaman, önceki durum, sonrası).

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
- Asayiş haberlerinde (cinayet, saldırı, kaza) olayı açıkça ve sade anlat; ama kanlı ayrıntı, "vahşet",
  "dehşet" gibi abartılı sözcükler ve ünlem kullanma.
- Kamuya mal olmamış kişilerin (mağdur, şüpheli, yakınları) tam adını YAZMA; yaş, ilçe, yakınlık yeterli
  ("19 yaşındaki kızı", "Mamak'ta bir baba"). Çocukların kimliğini belli edecek hiçbir bilgi verme.
- Henüz kanıtlanmamış suçlamaları kesinmiş gibi yazma: "iddia edildi", "suç duyurusunda bulundu",
  "gözaltına alındı" gibi durumu olduğu gibi anlat.

BİÇİM:
- Toplam 30–120 kelime. Metnin TAMAMI Facebook açıklamasına yazılır; görsele ise baştan sığdığı kadar
  satır konur. Bu yüzden İLK paragraf (kalın ana cümle ya da alıntı) tek başına okunduğunda olayı anlatmalı,
  ayrıntılar ve arka plan alttaki maddelerde olmalı (önemliden aza doğru).
- Her madde ve her paragraf TAM bir cümle olmalı ve nokta ile bitmeli. Hiçbir cümleyi yarıda bırakma. Tek cümlelik, bağlamsız metin YAZMA; okuyan neden önemli olduğunu anlamalı.
- **kalın**: konuşanın adı, ana cümle ya da en kritik ifade. Rakamlar normal kalabilir.
- Paragrafları boş satırla ayır. Madde satırları "— " ile başlar, aralarında boş satır olmaz.
- Emoji, hashtag, site/kaynak adı, "son dakika" yazma.

SOSYAL MEDYA KAYNAĞI: Kaynaklar arasında yalnızca "SOSYAL MEDYA PAYLAŞIMI" varsa, metni kendi cümlelerinle
yaz (paylaşımın cümlelerini kopyalama). Bir kişinin açıklaması ise sözü tırnak içinde aktarabilirsin.
Kişinin kendi açıklaması değilse temkinli yaz: "… iddia edildi", "… olduğu öne sürüldü".

Yanıtı YALNIZCA şu biçimde ver (JSON KULLANMA):
KATEGORİ: TÜRKİYE | DÜNYA | EKONOMİ | SPOR
KİŞİ: (haberin merkezindeki tanınmış kişinin tam adı; yoksa boş bırak)
---
(metin)"""


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
    for it in sorted(cluster.usable, key=lambda i: (not i.anchor,)):
        if it.group in groups or len(parts) >= max_sources:
            continue
        if it.social:
            body = it.summary
            head = f"### SOSYAL MEDYA PAYLAŞIMI ({it.source}) — haber sitesinde teyit edilmemiş olabilir"
        else:
            body = _article_text(it.link) or it.summary
            head = f"### {it.title}"
        if body:
            parts.append(f"{head}\n{body}")
            groups.add(it.group)
    return "\n\n".join(parts)


def _call_claude(source_text: str, model: str, key: str, feedback: str = "") -> dict:
    user = f"Kaynak metinler:\n\n{source_text}"
    if feedback:
        user += f"\n\nÖNCEKİ YANITIN REDDEDİLDİ: {feedback}. Kurallara uyarak yeniden yaz."
    r = requests.post(API_URL, timeout=60, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 900, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]})
    js = r.json()
    if "error" in js:
        raise RuntimeError("API: " + str(js["error"].get("message")))
    if js.get("stop_reason") == "max_tokens":
        raise ValueError("yanıt yarıda kesildi (uzunluk sınırı)")
    raw = "".join(b.get("text", "") for b in js.get("content", []))
    data = _parse(raw)
    text = _repair((data.get("metin") or "").strip())
    _check_text(text)
    cat = (data.get("kategori") or "").strip().upper()
    person = (data.get("kisi") or "").strip(" .-")
    if len(person.split()) > 5 or person.lower() in ("yok", "boş", "-"):
        person = ""
    return {"text": text, "category": cat if cat in KATEGORILER else None, "mode": "claude", "person": person}


def _repair(t: str) -> str:
    """Küçük biçim hatalarını reddetmek yerine düzeltir."""
    t = t.replace('\\n', "\n").strip()
    # Eşleşmeyen kalın işaretleri: sondaki tek ** fazlalığını sil
    if t.count("**") % 2:
        i = t.rfind("**")
        t = t[:i] + t[i + 2:]
    # Açılmış ama kapanmamış tırnak: sona kapanış tırnağı ekle
    if t.count("“") > t.count("”"):
        t = t.rstrip() + "”"
    elif t.count("”") > t.count("“"):
        t = "“" + t if not t.startswith("**") else t.replace("”", "\"", t.count("”") - t.count("“"))
    if t.count('"') % 2:
        t = t.replace('"', "")
    return t


def _parse(raw: str) -> dict:
    """Model yanıtını okur. Önce düz metin biçimi (KATEGORİ: ... / --- / metin), sonra JSON denenir."""
    raw = raw.strip()
    m = re.match(r"(?is)\s*KATEGOR[İI]\s*:\s*([^\n]+)\n(?:\s*K[İI]Ş[İI]\s*:\s*([^\n]*)\n)?\s*-{3,}\s*\n(.*)$", raw)
    if m:
        return {"kategori": m.group(1).strip(), "kisi": (m.group(2) or "").strip(), "metin": m.group(3).strip()}
    j = re.search(r"\{.*\}", raw, re.S)
    if j:
        try:
            return json.loads(j.group(0), strict=False)
        except Exception:
            mm = re.search(r'"metin"\s*:\s*"(.*)"\s*\}\s*$', j.group(0), re.S)   # son alana kadar her şey
            if mm:
                kat = re.search(r'"kategori"\s*:\s*"([^"]*)"', j.group(0))
                return {"kategori": kat.group(1) if kat else "",
                        "metin": mm.group(1).replace('\\n', "\n").replace('\\"', '"')}
    if raw and len(raw.split()) >= 12 and "{" not in raw:
        return {"kategori": "", "metin": raw}
    raise ValueError("yanıt okunamadı")


def _check_text(text: str):
    """Yarım, kesik ya da bozuk metni paylaşmaya izin vermez."""
    t = text.strip()
    if not t:
        raise ValueError("metin boş")
    if len(t.split()) > 150:
        raise ValueError("metin çok uzun")
    if len(re.sub(r"\*\*", "", t).split()) < 12:
        raise ValueError("metin çok kısa, bağlam yok")
    if t.endswith(("...", "…")) or re.search(r"\w(\.\.\.|…)\s*$", t):
        raise ValueError("metin yarıda kesilmiş")
    if t.count("“") != t.count("”") or t.count('"') % 2 or t.count("**") % 2:
        raise ValueError("tırnak/kalın işaretleri eşleşmiyor")
    # HER satır (maddeler dahil) tam cümle olarak bitmeli. Model kelime sınırına sığmak için cümleyi
    # yarıda bırakabiliyor ("— Valilik ... buzlanma riskine"); bu durumda metin yeniden yazdırılır.
    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        end = re.sub(r"[*”\"’')\s]+$", "", line)
        if end and end[-1] not in ".!?:%" and not end[-1].isdigit():
            raise ValueError(f"cümle yarım kalmış: '{line[-40:]}'. Her madde tam cümle olmalı ve noktayla bitmeli; "
                             "sığmıyorsa madde sayısını azalt")


def _clean_sentence(summary: str, title: str) -> str | None:
    """RSS özetinden yalnızca TAM bir cümle alır; '...' ile kesilmiş özetleri asla kullanmaz."""
    s = re.sub(r"\s+", " ", summary or "").strip()
    s = re.sub(r"\s*(\[\.\.\.\]|\[…\]|\.\.\.|…)\s*$", " …", s)   # kesik sonu işaretle
    for m in re.finditer(r"(.{30,260}?[.!?])(?=\s|$)", s):
        cand = m.group(1).strip()
        if "…" in cand or "..." in cand:
            continue
        if cand.lower()[:30] != title.lower()[:30]:
            return cand
        break
    return None


def fallback(cluster) -> dict:
    site = [i for i in cluster.usable if not i.social]
    lead = sorted(site, key=lambda i: (not i.anchor, abs(len(i.title) - 70)))[0] if site else cluster.lead()
    head = lead.title.strip().rstrip(".").rstrip()
    text = f"**{head}**" if head.endswith(("?", "!")) else f"**{head}.**"
    sent = _clean_sentence(lead.summary, lead.title)
    if sent:
        text += "\n\n" + sent
    return {"text": text, "category": None, "mode": "yedek"}


LAST_ERRORS: list[str] = []


def write(cluster, model: str, log=print) -> dict | None:
    """Anahtar varsa metni Claude yazar. Reddedilen yanıt, ret nedeniyle birlikte tekrar yazdırılır (3 deneme).
    Yine olmazsa, temiz bir yedek metin kuralları geçiyorsa o kullanılır; geçmiyorsa haber bu tur atlanır."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    social_only = not any(not i.social for i in cluster.usable)
    if not key:
        if social_only:
            return None
        log("  (ANTHROPIC_API_KEY yok; basit metin kullanılıyor)")
        return fallback(cluster)
    src = gather_sources(cluster)
    feedback = ""
    for attempt in (1, 2, 3):
        try:
            return _call_claude(src, model, key, feedback)
        except Exception as e:
            feedback = str(e)[:160]
            msg = f"{e.__class__.__name__}: {feedback}"
            LAST_ERRORS.append(f"{cluster.lead().title[:60]} -> {msg}")
            log(f"  ! Metin yazımı başarısız (deneme {attempt}: {msg[:100]})")
            if feedback.startswith("API:"):
                break   # API hatası (kredi, erişim): tekrar denemek boşuna
    if social_only:
        return None          # yalnızca sosyal medya kaynağı varsa onun metniyle yedek kurma
    fb = fallback(cluster)
    try:
        _check_text(fb["text"])
        log("  Yedek metin kullanıldı.")
        return fb
    except ValueError:
        return None


def plain(markup: str) -> str:
    """Açıklama için **işaretleri** kaldırılmış düz metin."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", markup, flags=re.S).replace("**", "").strip()
