"""Ağ bağlantısı olmadan doğrulama mantığını test eder:  python -m tests.test_pipeline"""
from datetime import datetime, timezone
from dh.collect import parse_feed
from dh.verify import cluster, verified

def rss(items):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    body = "".join(f"<item><title>{t}</title><link>https://x/{i}</link><pubDate>{now}</pubDate>"
                   f"<description>{t} ile ilgili ayrıntılar geliyor.</description></item>" for i, t in enumerate(items))
    return f"<rss><channel>{body}</channel></rss>".encode()

feeds = {
 ("Anadolu Ajansı","aa",True): ["Kapadokya'da peribacası çöktü: 2 kişi hayatını kaybetti", "Merkez Bankası faizi sabit tuttu"],
 ("Hürriyet","demiroren",False): ["Kapadokya'da peribacası çöktü! Ölenlerin kimlikleri belli oldu"],
 ("CNN Türk","demiroren",False): ["Kapadokya'da peribacası çöktü: ölü sayısı 2"],
 ("Sözcü","sozcu",False): ["Kapadokya'da peribacası çöktü, 2 turist öldü", "Ünlü şarkıcıdan şok paylaşım"],
 ("NTV","dogus",False): ["Nevşehir Kapadokya'da peribacası çökmesi: 2 ölü", "Merkez Bankası faiz kararını açıkladı: faiz sabit"],
 ("Habertürk","ciner",False): ["Ünlü şarkıcıdan şok paylaşım"],
}
items = []
for (n, g, a), titles in feeds.items():
    items += parse_feed(rss(titles), {"name": n, "group": g, "anchor": a})
cs = cluster(items, 0.34)
ok = verified(cs, 3, True)
for c in cs:
    print(f"{len(c.groups)} grup | anchor={c.has_anchor} | {c.lead().title} | {c.sources}")
assert len(ok) == 1 and "peribaca" in ok[0].lead().title.lower(), "Peribacası haberi doğrulanmalı"
assert len(ok[0].groups) == 4, "Hürriyet+CNN Türk tek grup sayılmalı (4 grup)"
print("\nTEST GEÇTİ: yalnızca 3+ bağımsız gruptan + ajans teyitli haber seçildi")
