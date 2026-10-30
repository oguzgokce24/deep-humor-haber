"""RSS/Atom akışlarından haber toplama (yalnızca standart kütüphane + requests)."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import requests

UA = "Mozilla/5.0 (compatible; DeepHumorHaberBot/1.0)"
NS_MEDIA = "{http://search.yahoo.com/mrss/}"
NS_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Item:
    source: str
    group: str
    anchor: bool
    title: str
    link: str
    summary: str = ""
    image: str | None = None
    published: datetime | None = None
    tokens: set = field(default_factory=set)


def _text(el, *tags):
    for t in tags:
        x = el.find(t)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return ""


def clean_html(s: str) -> str:
    s = re.sub(r"<!--.*?-->", " ", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(s: str):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone(timedelta(hours=3)))  # TR yerel saat varsayımı
    return d.astimezone(timezone.utc)


def _find_image(el) -> str | None:
    for tag in ("enclosure",):
        e = el.find(tag)
        if e is not None and "image" in (e.get("type") or "image"):
            if e.get("url"):
                return e.get("url")
    for tag in (NS_MEDIA + "content", NS_MEDIA + "thumbnail"):
        e = el.find(tag)
        if e is not None and e.get("url"):
            return e.get("url")
    g = el.find(NS_MEDIA + "group")
    if g is not None:
        e = g.find(NS_MEDIA + "content")
        if e is not None and e.get("url"):
            return e.get("url")
    for tag in ("imageUrl", "image", "img"):
        e = el.find(tag)
        if e is not None:
            v = (e.text or "").strip() or e.get("url") or ""
            if v.startswith("http"):
                return v
            u = e.find("url")
            if u is not None and (u.text or "").startswith("http"):
                return u.text.strip()
    raw = ET.tostring(el, encoding="unicode")
    m = re.search(r'(?:src|href)=["\'](https?://[^"\']+\.(?:jpe?g|png|webp)[^"\']*)', html.unescape(raw), re.I)
    return m.group(1) if m else None


def parse_feed(xml_bytes: bytes, src: dict) -> list[Item]:
    root = ET.fromstring(xml_bytes)
    out = []
    entries = root.iter("item")
    entries = list(entries) or list(root.iter(NS_ATOM + "entry"))
    for el in entries:
        title = clean_html(_text(el, "title", NS_ATOM + "title"))
        if not title:
            continue
        link = _text(el, "link")
        if not link:
            le = el.find(NS_ATOM + "link")
            link = le.get("href", "") if le is not None else ""
        summary = clean_html(_text(el, "description", NS_ATOM + "summary", NS_ATOM + "content"))
        pub = _parse_date(_text(el, "pubDate", NS_ATOM + "published", NS_ATOM + "updated",
                                "{http://purl.org/dc/elements/1.1/}date"))
        out.append(Item(src["name"], src["group"], bool(src.get("anchor")), title, link,
                        summary[:600], _find_image(el), pub))
    return out


def fetch_all(sources: list[dict], max_age_hours: float, log=print) -> list[Item]:
    now = datetime.now(timezone.utc)
    items: list[Item] = []
    for s in sources:
        try:
            r = requests.get(s["url"], headers={"User-Agent": UA}, timeout=20)
            r.raise_for_status()
            got = parse_feed(r.content, s)
        except Exception as e:
            log(f"  ! {s['name']}: {e.__class__.__name__}: {str(e)[:80]}")
            continue
        fresh = [i for i in got if i.published is None or now - i.published <= timedelta(hours=max_age_hours)]
        log(f"  {s['name']}: {len(fresh)}/{len(got)} güncel")
        items.extend(fresh)
    return items


def og_image(url: str) -> str | None:
    """RSS'te görsel yoksa haber sayfasındaki og:image etiketini dener."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', r.text, re.I)
        return html.unescape(m.group(1)) if m else None
    except Exception:
        return None
