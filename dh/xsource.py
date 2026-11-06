"""X (Twitter) hesaplarını erken uyarı kaynağı olarak okur (resmi X API v2).

Bu hesapların paylaşımlarından yalnızca OLAY ve BİLGİ alınır. Metin yapay zekâ ile kendi
cümlelerimizle yeniden yazılır; bu hesapların metni ya da fotoğrafı aynen kullanılmaz.
X_BEARER_TOKEN gizli anahtarı yoksa bu kaynak sessizce atlanır.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import requests

from dh.collect import Item

API = "https://api.x.com/2"


def _get(path: str, token: str, **params):
    r = requests.get(f"{API}{path}", params=params, timeout=20,
                     headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 429:
        raise RuntimeError("X API kota/hız sınırı")
    js = r.json()
    if r.status_code >= 400 or ("errors" in js and "data" not in js):
        raise RuntimeError(f"X API {r.status_code}: {str(js.get('errors') or js.get('detail') or js)[:120]}")
    return js


def _title_from(text: str) -> str:
    t = re.sub(r"https?://\S+", "", text).strip()
    t = re.sub(r"\s+", " ", t)
    first = re.split(r"(?<=[.!?:])\s|\n", t, maxsplit=1)[0]
    return (first if len(first) >= 25 else t)[:160]


def fetch_x(accounts: list[dict], st: dict, log=print) -> list[Item]:
    """accounts: [{"username": "bpthaber", "name": "BPT"}, ...]. st["x"] kullanıcı kimliği ve since_id tutar."""
    token = os.environ.get("X_BEARER_TOKEN")
    if not token or not accounts:
        return []
    xs = st.setdefault("x", {})
    out: list[Item] = []
    for acc in accounts:
        u = acc["username"].lstrip("@")
        info = xs.setdefault(u, {})
        try:
            if "id" not in info:
                info["id"] = _get(f"/users/by/username/{u}", token)["data"]["id"]
            params = {"max_results": 10, "exclude": "retweets,replies", "tweet.fields": "created_at"}
            if info.get("since_id"):
                params["since_id"] = info["since_id"]
            js = _get(f"/users/{info['id']}/tweets", token, **params)
        except Exception as e:
            log(f"  ! X @{u}: {str(e)[:100]}")
            continue
        tweets = js.get("data", [])
        if js.get("meta", {}).get("newest_id"):
            info["since_id"] = js["meta"]["newest_id"]
        # İlk çalıştırmada geçmiş paylaşımları yayınlama: sadece başlangıç noktası kaydedilir
        if not info.get("started"):
            info["started"] = True
            log(f"  X @{u}: başlangıç noktası kaydedildi")
            continue
        for t in tweets:
            text = t.get("text", "")
            if len(text) < 40:
                continue
            pub = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")) if t.get("created_at") \
                else datetime.now(timezone.utc)
            out.append(Item(source=f"{acc.get('name', u)} (X)", group=f"x_{u}", anchor=False,
                            title=_title_from(text), link=f"https://x.com/{u}/status/{t['id']}",
                            summary=text[:1200], image=None, published=pub, social=True))
        log(f"  X @{u}: {len(tweets)} yeni paylaşım")
    return out
