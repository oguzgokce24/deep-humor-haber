"""Haberleri kümeleme ve çok kaynaklı doğrulama."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

STOP = set("""
ve ile de da ki bu şu o bir için gibi daha çok en mi mı mu mü ne ya veya ama fakat
olarak oldu olan olduğu olduğunu etti eden edildi yaptı yapılan sonra önce kadar
son dakika flaş açıklama açıkladı dedi söyledi açıklandı haber haberi video foto
galeri canlı izle işte belli tarafından üzerine hakkında yeni ilk her tüm bütün
""".split())


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def tokens(title: str) -> set[str]:
    words = re.findall(r"[a-zçğıöşüâîû0-9]+", tr_lower(title))
    out = set()
    for w in words:
        if w in STOP or (len(w) < 3 and not w.isdigit()):
            continue
        # Türkçe ekler nedeniyle kelimenin ilk 5 harfi (gövde yaklaşık) kullanılır
        out.add(w[:5])
    return out


# Haber başlıklarında çok sık geçen, tek başına aynı olayı göstermeyen kelime gövdeleri
WEAK = {w[:5] for w in """
operasyon gözaltı gözaltına soruşturma soruşturmasında tutuklandı tutuklama kişi kişiye kişinin
yaralı yaralandı hayatını kaybetti öldü ölü kaza kazada saldırı saldırısı karar kararı açıklaması
dalga yeni milyon lira dolar türkiye türk istanbul ankara bakan bakanı başkanı cumhurbaşkanı
il ilde ilçe merkezli şüpheli yakalandı ele geçirildi polis jandarma mahkeme dava
""".split()}


def _strong(tok: str) -> bool:
    return tok not in WEAK and not tok.isdigit()


def similarity(a: set, b: set) -> float:
    """Ortak kelimelerden en az 2'si ayırt edici olmalı (ya da 1 ayırt edici + 2 genel/sayı).
    Böylece 'operasyon: 10 gözaltı' gibi kalıplar farklı olayları birleştirmez."""
    if not a or not b:
        return 0.0
    common = a & b
    strong = sum(1 for t in common if _strong(t))
    weak = len(common) - strong
    if not (strong >= 2 or (strong == 1 and weak >= 2)):
        return 0.0
    return 2 * len(common) / (len(a) + len(b))


@dataclass
class Cluster:
    items: list = field(default_factory=list)

    @property
    def groups(self) -> set[str]:
        return {i.group for i in self.items}

    @property
    def has_anchor(self) -> bool:
        return any(i.anchor for i in self.items)

    @property
    def fingerprint(self) -> set[str]:
        c = Counter(t for i in self.items for t in i.tokens)
        need = max(2, len(self.groups) // 2)
        return {t for t, n in c.items() if n >= need} or set().union(*(i.tokens for i in self.items))

    @property
    def latest(self):
        ds = [i.published for i in self.items if i.published]
        return max(ds) if ds else None

    @property
    def usable(self):
        """Başlık/metin/fotoğraf alınabilecek kaynaklar (yalnızca-teyit olanlar hariç)."""
        return [i for i in self.items if not i.verify_only]

    @property
    def sources(self) -> list[str]:
        seen, out = set(), []
        for i in sorted(self.items, key=lambda x: (x.verify_only, x.source)):
            if i.source not in seen:
                seen.add(i.source)
                out.append(i.source)
        return out

    def lead(self):
        """Başlık için temsilci haber: yalnızca kullanılabilir kaynaklardan, makul uzunlukta olan."""
        cands = sorted(self.usable or self.items, key=lambda i: (not i.anchor, abs(len(i.title) - 70)))
        return cands[0]

    def best_image(self):
        for i in sorted(self.usable, key=lambda i: (not i.anchor,)):
            if i.image:
                return i.image, i.source
        return None, None


def cluster(items, threshold: float) -> list[Cluster]:
    for i in items:
        i.tokens = tokens(i.title)
    clusters: list[Cluster] = []
    for it in items:
        if len(it.tokens) < 2:
            continue
        best, best_s = None, 0.0
        for c in clusters:
            s = max(similarity(it.tokens, o.tokens) for o in c.items)
            if s > best_s:
                best, best_s = c, s
        if best is not None and best_s >= threshold:
            best.items.append(it)
        else:
            clusters.append(Cluster([it]))
    return clusters


def verified(clusters, min_groups: int, require_anchor: bool) -> list[Cluster]:
    ok = [c for c in clusters if len(c.groups) >= min_groups and (c.has_anchor or not require_anchor)
          and c.usable]
    # En çok bağımsız grubun verdiği ve en yeni haberler öne
    ok.sort(key=lambda c: (len(c.groups), c.latest.timestamp() if c.latest else 0), reverse=True)
    return ok
