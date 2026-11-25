# W27 Heilbronn başvuru botu

Bot, [apartments-hn.de/apartment-mieten](https://www.apartments-hn.de/apartment-mieten) sayfasını GitHub Actions üzerinde 7/24 izler. Bir daire **"Apply now"** durumuna geçtiğinde ve filtrelerine uyduğunda Telegram'a doğrudan başvuru linkini gönderir. Kontroller yaklaşık 90 saniyede bir yapılır.

## Kurulum (yaklaşık 10 dakika)

### 1. Telegram botu
1. Telegram'da **@BotFather**'a `/newbot` yaz, bota bir isim ver. Sana bir **token** verecek (`123456:ABC...` gibi).
2. Yeni botuna herhangi bir mesaj at (örneğin "merhaba").
3. Tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini aç. Çıkan sonuçta `"chat":{"id":123456789` kısmındaki sayı senin **chat id**'n.

### 2. GitHub reposu
1. GitHub'da yeni bir repo oluştur, **Public** olsun. Public repolarda Actions dakikaları sınırsız. Private repoda aylık 2000 dakika sınırı var, bu bot ise ayda yaklaşık 4000 dakika kullanır. Kodda gizli bilgi bulunmuyor, token'lar şifreli Secrets'ta saklanıyor.
2. Bu klasördeki her şeyi (`.github` klasörü dahil) repoya yükle.

### 3. Ayarlar
**Settings → Secrets and variables → Actions** sayfasında:

**Secrets** sekmesi (zorunlu):
| İsim | Değer |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather'ın verdiği token |
| `TELEGRAM_CHAT_ID` | chat id'n |

**Variables** sekmesi (isteğe bağlı filtreler, boş bırakırsan her daire için haber verir):
| İsim | Örnek | Anlamı |
|---|---|---|
| `W27_TYPES` | `Single` | Tipinde bunlardan biri geçenler (virgülle ayır). `Single` veya `Partner` |
| `W27_EXCLUDE_TYPES` | `barrier-free,limited furnishing` | Tipinde bunlar geçenleri atla |
| `W27_MAX_RENT` | `505.5` | Bu kiradan pahalı olanları atla |
| `W27_EARLIEST` | `2027-03-01` | Bu tarihten önce taşınma olanları atla |
| `W27_LATEST` | `2027-05-01` | Bu tarihten sonra taşınma olanları atla |

> Engelli dostu (barrier-free) daireler en fazla 3 ay kiralanıyor ve belge istiyor. İhtiyacın yoksa `W27_EXCLUDE_TYPES`'a ekle.

### 4. Test
**Actions → W27 watcher → Run workflow** yolunu izle, **"Only send a Telegram test message"** kutusunu işaretleyip çalıştır. Telegram'a test mesajı gelmeli.
Ardından kutuyu işaretlemeden bir kez daha çalıştır. İlk çalıştırmada şu an açık olan ve filtrene uyan daireler bildirilir. Sonrasında bot her 10 dakikada bir kendiliğinden çalışır.

## Bilmen gerekenler
- **Hız:** GitHub zamanlanmış görevleri bazen 5-20 dakika gecikmeyle başlatır, yoğun saatlerde nadiren bir çalıştırmayı atlar. Bot bu yüzden her çalıştırmada 9 dakika boyunca 90 saniyede bir kontrol ediyor. Yine de arada boşluklar olabilir.
- **Başvuru:** W27 başvuruları elle inceliyor ve sözleşmeyi 5 gün içinde imzalayıp yüklemen gerekiyor. REOS hesabını ve belgelerini (kimlik/pasaport, öğrenci belgesi veya kabul mektubu, AB dışındansan oturum izni/vize) önceden hazır tut. Bildirim gelince "Giriş yap ve başvur" linkiyle 2-3 dakikada başvurabilirsin.
- **Durdurmak için:** Actions → W27 watcher → sağ üstteki "…" menüsü → **Disable workflow**.
