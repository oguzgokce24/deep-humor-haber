# Deep Humor Haber Otomasyonu

17 haber kaynağını 15 dakikada bir tarar. Aynı haberi **farklı medya gruplarından en az 3 kaynak + en az 1 ajans/kamu/uluslararası kaynak** veriyorsa doğrulanmış sayar, Deep Humor şablonunda görselini hazırlar ve **doğrudan Facebook sayfanda paylaşır**. Onay adımı yoktur.

```
RSS kaynakları ─► kümeleme ─► doğrulama (≥3 grup + çapa) ─► görsel ─► Facebook
```

Tamamen ücretsiz çalışır (GitHub Actions + Facebook Graph API). Bilgisayarının açık olması gerekmez.
Paylaşım hızı: iki paylaşım arası en az 25 dk → saatte en fazla 2 haber.

---

## Kurulum (yaklaşık 15 dakika, bir kere yapılır)

### 1) Facebook sayfa anahtarı
1. https://developers.facebook.com → **Uygulamalarım → Uygulama Oluştur** → tür olarak **İşletme (Business)** seç.
2. **Araçlar → Graph API Gezgini**'ni aç, sağ üstte uygulamanı seç.
3. **İzinler**'e şunları ekle: `pages_show_list`, `pages_manage_posts`, `pages_read_engagement` → **Generate Access Token** → Deep Humor sayfasını seçip onayla.
4. Bu kısa ömürlü anahtarı **Araçlar → Erişim Anahtarı Hata Ayıklayıcısı**'na yapıştır → en altta **Erişim Anahtarını Uzat**. Çıkan uzun ömürlü anahtarı kopyala.
5. Graph API Gezgini'nde anahtar kutusuna bu uzun ömürlü anahtarı yapıştır, sorguya `me/accounts` yaz → **Gönder**.
6. Sonuçta Deep Humor'un yanındaki:
   - `access_token` → `FB_PAGE_TOKEN` (bu sayfa anahtarının süresi dolmaz)
   - `id` → `FB_PAGE_ID`

> Uygulamanın "Geliştirme" modunda kalması sorun değil; sayfanın yöneticisi sen olduğun için kendi sayfana paylaşım yapabilir. Uygulama incelemesine gerek yok.

### 2) GitHub
1. https://github.com → **New repository** → ad: `deep-humor-haber`.
   - **Public** önerilir: Actions dakikaları sınırsız ve ücretsiz. Gizli anahtarlar yine gizli kalır.
   - **Private** seçersen aylık 2000 dakika sınırı var; `.github/workflows/haber.yml` içindeki `*/15` değerini `*/30` yap.
2. **Add file → Upload files** ile bu klasördeki her şeyi yükle. `.github` gizli klasör olduğu için Mac/Windows'ta görünmeyebilir; yüklenmediyse **Add file → Create new file** ile adı `.github/workflows/haber.yml` olan dosya oluşturup içeriğini yapıştır.
3. **Settings → Secrets and variables → Actions → New repository secret** ile `FB_PAGE_TOKEN` anahtarını ekle.
   Sayfa kimliği `config.yaml` içindeki `page_id` alanında yazıyor.
4. **Actions** sekmesi → iş akışlarını etkinleştir → **Deep Humor Haber → Run workflow** ile ilk çalıştırmayı başlat.

Doğrulanmış bir haber varsa birkaç dakika içinde sayfanda ilk paylaşım görünür.

---

## Windows bilgisayarda çalıştırma (önerilen: 3 dakikada bir tarama)
1. Bu klasörü örneğin `Belgeler\DeepHumorHaber` içine koy.
2. **KUR.bat**'a çift tıkla. Python yoksa kurar, gerekli paketleri yükler, Not Defteri'nde
   `anahtarlar.txt` dosyasını açar (Facebook ve isteğe bağlı Claude anahtarını yapıştır, kaydet, kapat),
   sonra Görev Zamanlayıcı'ya her 3 dakikada bir arka planda çalışan bir görev ekler.
3. **KAYITLAR.bat** ile son çalışmaları görebilirsin. **DENE.bat** paylaşmadan deneme yapar.
   **KALDIR.bat** otomasyonu durdurur.
- Bilgisayar uyku moduna geçerse otomasyon da durur: Ayarlar → Sistem → Güç → "Uyku: Hiçbir zaman".
- Bilgisayarda çalıştırırken GitHub'daki zamanlanmış çalıştırma kapatılmalı, yoksa aynı haber iki kez paylaşılabilir.
- Depo **açıksa** GitHub zaten kesintisiz (3 dakikada bir) çalışır; o durumda bilgisayar kurulumuna gerek yoktur.

## Bağlamlı metin (isteğe bağlı ama önerilir)
Görseldeki ve açıklamadaki metin, haberin tam metni okunarak Claude API ile **kendi cümlelerimizle** yazılır:
alıntı (Kişi: “söz”), maddeli (ana cümle + — bağlam maddeleri) ya da kısa kalıp. Görseldeki metin ile
Facebook açıklaması aynıdır. Bunun için depoya `ANTHROPIC_API_KEY` gizli anahtarını ekle
(console.anthropic.com → API Keys). Anahtar yoksa başlık + özet cümlesi kullanılır.

## Takip
- **Actions** sekmesinde her çalışmanın kaydı var: hangi kaynaklar tarandı, ne paylaşıldı, haberin geçtiği tüm kaynak linkleri.
- `state/state.json` dosyasında paylaşılan son 200 haber ve kaynak linkleri tutulur.
- Bir paylaşımı beğenmezsen Facebook'tan silmen yeterli; aynı haber tekrar paylaşılmaz.
- Otomasyonu durdurmak için: **Actions → Deep Humor Haber → ⋯ → Disable workflow**.

## Ayarlar (`config.yaml`)
- `verify.min_groups` — kaç bağımsız medya grubu gereksin (varsayılan 3). Daha temkinli olmak için 4 yap.
- `verify.require_anchor` — AA / TRT / BBC / DW / Euronews'ten en az biri şart mı
- `publish.min_gap_minutes` — iki paylaşım arası en az süre (varsayılan 25 dk)
- `theme` — renk tonu (4 hazır ton var, config içinde yazıyor), `brand` — şeritteki isim, logo harfleri, hashtag'ler
- **Kendi logon:** `assets/logo.png` adıyla kare bir logo koy; yuvarlak çerçevenin içine otomatik yerleşir.
- **Başka yazı tipi:** `assets/fonts/Headline.ttf` koyarsan başlıklar o yazı tipiyle çıkar (ör. Google Fonts'tan Rubik Bold).
- `sources` — kaynak ekle/çıkar. **Aynı patrona ait sitelere aynı `group` değerini ver**; doğrulamada tek kaynak sayılırlar.

Sol şeritte haberin konusu yazar (TÜRKİYE / DÜNYA / EKONOMİ / SPOR). Teyit ve fotoğraf kaynağı gönderide gösterilmez; kaynak linkleri Actions kayıtlarında ve state/state.json'da tutulur.

## Bilgisayarında deneme
```bash
pip install -r requirements.txt
python main.py --dry-run          # Facebook'a dokunmaz, görseller out/ klasörüne
python -m tests.test_pipeline     # doğrulama mantığı testi
```

## Bilmen gerekenler
- **Onaysız paylaşım:** "3 bağımsız kaynak + ajans" kuralı yanlış haber riskini ciddi azaltır ama sıfırlamaz; ajansların hep beraber hatalı geçtiği ya da sonradan düzeltilen haberler nadiren olur. Sayfayı ara ara kontrol etmen iyi olur.
- **Fotoğraf telifi:** Görseller haber sitelerinin fotoğraflarını kullanır ve kaynağı yazar. Kaynak belirtmek telif iznini karşılamaz; Facebook'a telif bildirimi gelirse gönderi kaldırılır, tekrarında sayfa kısıtlanabilir. Bildirim gelirse fotoğrafsız tasarıma geçmek kolay.
- Sayfa kategorisini Facebook'ta **Medya/Haber Şirketi** yapman erişimi olumlu etkiler.
- Bir RSS adresi değişirse Actions kaydında `! Kaynak adı: HTTPError` görürsün; `config.yaml`'dan güncellemen yeterli.
