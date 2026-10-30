"""Facebook sayfa paylaşımı (yalnızca Facebook; Instagram'a paylaşım yapılmaz)."""
from __future__ import annotations

import requests


class FacebookPage:
    """FB_PAGE_TOKEN olarak sistem kullanıcısı anahtarı da, sayfa anahtarı da verilebilir.
    Sistem kullanıcısı anahtarı verilirse paylaşımdan önce sayfa anahtarına çevrilir."""

    def __init__(self, page_id: str, token: str, version: str = "v21.0"):
        self.base = f"https://graph.facebook.com/{version}"
        self.page_id = page_id
        self.token = token
        self._page_token: str | None = None

    def _token_for_page(self) -> str:
        if self._page_token:
            return self._page_token
        r = requests.get(f"{self.base}/{self.page_id}", params={"fields": "access_token", "access_token": self.token},
                         timeout=30)
        js = r.json()
        # Zaten sayfa anahtarıysa access_token alanı dönmeyebilir; o durumda verilen anahtar kullanılır
        self._page_token = js.get("access_token") or self.token
        return self._page_token

    def post_photo(self, image_bytes: bytes, message: str) -> str:
        r = requests.post(f"{self.base}/{self.page_id}/photos",
                          data={"message": message, "access_token": self._token_for_page(), "published": "true"},
                          files={"source": ("haber.jpg", image_bytes, "image/jpeg")}, timeout=120)
        js = r.json()
        if "error" in js:
            raise RuntimeError(f"Facebook: {js['error'].get('message')}")
        return js.get("post_id") or js.get("id")
