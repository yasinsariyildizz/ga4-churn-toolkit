# GA4 Churn Toolkit — Türkçe Analiz ve Yorumlama Rehberi

Bu doküman, `ga4-churn-toolkit` içindeki satın alma bazlı churn analizinin yöntemini, çıktılarını ve yorumlama biçimini açıklar. Amaç yalnızca kodun nasıl çalıştırıldığını göstermek değil; üretilen sayıların hangi soruya cevap verdiğini, hangi durumda nasıl yorumlanması gerektiğini ve hangi sonuçların çıkarılmaması gerektiğini netleştirmektir.

Analiz üç kullanıcı durumu üretir:

```text
active_purchaser
pre_churn
churned
```

Örnek kullanım:

```python
analysis.churn_analysis(60, 90)
```

Bu örnekte sınıflandırma şöyledir:

```text
Son alışverişten 0–60 gün geçmişse     → active_purchaser
Son alışverişten 61–90 gün geçmişse    → pre_churn
Son alışverişten 90 günden fazla geçmişse → churned
```

Analiz gelecekte kimin churn olacağını tahmin etmez. Mevcut GA4 geçmişine bakarak, tanımlanan gün sınırlarına göre mevcut kullanıcı durumunu sınıflandırır.

---

# 1. Analizde hangi kullanıcı kimliği kullanılır?

Bu sürümde bütün hesaplamalar **`user_id` bazında** yapılır.

Kaynak GA4 verisinde yalnızca `user_id` dolu olan satırlar analize alınır:

```text
user_id IS NOT NULL
```

Bunun anlamı şudur: analiz, GA4 uygulamasında `user_id` atanmış tanımlı kullanıcıları kapsar. Sadece `user_pseudo_id` bulunan anonim kullanıcılar bu çalışmaya dahil edilmez.

Bu nedenle aşağıdaki iki sayı doğal olarak farklı olabilir:

```text
GA4 toplam kullanıcı: 1.200.000
user_id bulunan kullanıcı: 280.000
```

Churn analizi 280.000 kişilik tanımlı kullanıcı evreni üzerinden çalışır.

Bu fark bir hata değildir. Ancak sonuç raporlanırken kullanıcı kapsamı açık biçimde belirtilmelidir.

Önerilen ifade:

> Analiz, GA4 BigQuery export verisinde `user_id` bulunan tanımlı kullanıcılar üzerinden hesaplanmıştır.

### `user_id` kullanımının avantajı

Aynı `user_id` farklı cihaz ve oturumlarda gönderiliyorsa kullanıcı davranışı daha tutarlı biçimde birleştirilebilir. Bu, `user_pseudo_id` bazlı cihaz/tarayıcı seviyesindeki analize göre müşteri davranışına daha yakın bir görünüm sağlayabilir.

### Dikkat edilmesi gereken nokta

`user_id` implementasyonu eksik veya yalnızca belirli kullanıcı gruplarında varsa analiz bütün müşteri kitlesini temsil etmeyebilir. Örneğin sadece giriş yapan üyelerde `user_id` varsa sonuçlar daha sadık veya daha aktif bir kullanıcı grubuna doğru eğilebilir.

---

# 2. Analiz tarihi nasıl belirlenir?

Analiz tarihi ayrıca girilmez. Kaynak veride bulunan en güncel `event_date` kullanılır:

```text
analysis_date = MAX(event_date)
```

Örnek:

```text
Bugünün tarihi: 21 Eylül
BigQuery'deki son event_date: 18 Eylül
```

Bu durumda bütün süre hesapları 18 Eylül'e göre yapılır.

Örneğin son alışveriş tarihi 20 Haziran olan kullanıcı için:

```text
18 Eylül - 20 Haziran = 90 gün
```

hesabı yapılır.

Bu nedenle sonuç paylaşılmadan önce `analysis_date` mutlaka kontrol edilmelidir. Veri akışı birkaç gün durmuşsa churn ve pre-churn sınıfları gerçekte olması gerekenden daha düşük görünebilir.

---

# 3. Başlangıç bilgileri

Analiz şu bilgilerle başlatılır:

```python
analysis = ChurnAnalysis(
    project_id="your-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

| Alan | Açıklama |
|---|---|
| `project_id` | GA4 BigQuery export verisinin bulunduğu Google Cloud projesi |
| `dataset_id` | GA4 export dataset'i |
| `table_id` | Kaynak tablo veya tablo deseni. Genellikle `events_*` |
| `output_dataset_id` | Analiz tablolarının yazılacağı dataset |

Pre-churn ve churn gün sınırları başlangıçta verilmez. Önce satın alma aralıklarının incelenmesi, ardından gün sınırlarının belirlenmesi amaçlanır.

---

# 4. Önerilen çalışma sırası

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(60, 90)
```

Bu akış sırasıyla şu sorulara cevap verir:

```text
1. BigQuery ne kadar veri tarayacak?
2. Tanımlı kullanıcı ve alışveriş yapan kullanıcı kitlesi nasıl görünüyor?
3. Tekrar alışveriş yapan kullanıcılar normalde kaç günde geri dönüyor?
4. Hangi günlerden sonra kullanıcı pre-churn ve churn olarak sınıflandırılmalı?
5. Seçilen eşikler sonucunda kullanıcı dağılımı ve gelir görünümü nasıl değişiyor?
```

---

# 5. `dry_run()` — sorgu maliyeti ön kontrolü

```python
analysis.dry_run()
```

Bu fonksiyon ana analiz tablolarını oluşturmadan önce BigQuery'nin yaklaşık ne kadar veri tarayacağını gösterir.

Örnek çıktı:

```text
Estimated scan: 86.4 GB
```

Bu değer bir iş metriği değildir. Yalnızca sorgu hacmini ve olası BigQuery maliyetini kontrol etmek için kullanılır.

Özellikle `table_id="events_*"` kullanıldığında bütün geçmiş tablolar taranabilir.

### Örnek yorum

Beklenen veri hacmi son 6 ay için yaklaşık 100 GB iken dry run 2.7 TB gösteriyorsa aşağıdaki noktalar kontrol edilmelidir:

- yanlış dataset seçilmiş olabilir,
- beklenenden daha uzun geçmiş veri taranıyor olabilir,
- farklı GA4 property verileri aynı dataset içinde olabilir,
- test için tüm geçmişin taranmasına ihtiyaç olmayabilir.

`dry_run()` maliyet kontrolü içindir; churn sonucu veya kullanıcı davranışı hakkında yorum üretmez.

---

# 6. `create_base_table()` — kullanıcı bazlı temel analiz tablosu

```python
analysis.create_base_table()
```

Bu fonksiyon her `user_id` için tek satırlık bir özet tablo oluşturur.

Tablonun satır seviyesi:

```text
1 satır = 1 user_id
```

Ana çıktı tablosu:

```text
<output_dataset>.churn_base
```

## 6.1 Temel alanlar

| Alan | Açıklama |
|---|---|
| `user_id` | Analizde kullanılan kullanıcı kimliği |
| `first_event_date` | Kullanıcının kaynak veride ilk görüldüğü gün |
| `last_event_date` | Kullanıcının kaynak veride son görüldüğü gün |
| `event_count` | Kullanıcının toplam event sayısı |
| `session_count` | Kullanıcının toplam farklı `ga_session_id` sayısı |
| `purchase_count` | Kullanıcının toplam `purchase` event sayısı |
| `revenue` | GA4'te görülen toplam purchase revenue |
| `first_purchase_date` | İlk satın alma tarihi |
| `last_purchase_date` | Son satın alma tarihi |
| `analysis_date` | Kaynak verideki en güncel tarih |
| `days_since_last_purchase` | Son satın almadan analiz tarihine kadar geçen gün |

---

# 7. `create_base_table()` çıktıları nasıl yorumlanır?

## Users

Analize dahil edilen farklı `user_id` sayısıdır.

Bu sayı GA4 toplam kullanıcı sayısı değildir. Yalnızca `user_id` bulunan tanımlı kullanıcıları ifade eder.

Örnek:

```text
Users = 240.000
```

Bu çıktı, seçilen kaynak veri içinde 240.000 farklı `user_id` bulunduğunu gösterir.

## Purchasers

En az bir `purchase` event'i olan kullanıcı sayısıdır.

Örnek:

```text
Users      = 240.000
Purchasers = 72.000
```

Bu durumda analize dahil edilen tanımlı kullanıcıların 72.000'i en az bir satın alma yapmıştır.

Churn ve pre-churn oranlarının temel kitlesi bu 72.000 kullanıcıdır.

## One-time purchasers

Sadece bir purchase kaydı bulunan kullanıcı sayısıdır.

Örnek:

```text
Purchasers          = 72.000
One-time purchasers = 46.000
Repeat purchasers   = 26.000
```

Bu yapı, satın alma yapan kitlenin büyük kısmının ikinci satın almaya geçemediğini gösterebilir. Ancak bunun yorumlanabilmesi için veri geçmişinin yeterince uzun olması gerekir.

Örneğin dataset sadece son 30 günü içeriyorsa yeni müşteri olan birçok kişi henüz ikinci satın alma fırsatı bulmamış olabilir.

## Repeat purchasers

Birden fazla purchase kaydı bulunan kullanıcı sayısıdır.

`purchase_day_distribution()` fonksiyonundaki satın alma aralıkları esas olarak bu kullanıcıların davranışından oluşur.

## Purchaser rate

Formül:

```text
Purchasers / Users
```

Örnek:

```text
Users      = 240.000
Purchasers = 72.000
Purchaser rate = %30
```

Bu değer klasik GA4 e-ticaret dönüşüm oranı değildir. Oturum veya event bazında değil, kullanıcı bazında hesaplanır.

## Repeat rate

Formül:

```text
Repeat purchasers / Purchasers
```

Örnek:

```text
Purchasers        = 72.000
Repeat purchasers = 26.000
Repeat rate       = %36,1
```

Bu değer, satın alma yapan kullanıcıların ne kadarının birden fazla satın alma davranışı gösterdiğini özetler.

## Revenue

Kaynak GA4 purchase event'lerinden hesaplanan geçmiş gelir toplamıdır.

Bu değerin finans sistemiyle birebir aynı olması beklenmemelidir. Aşağıdaki sorunlar fark yaratabilir:

- duplicate purchase event,
- eksik purchase event,
- hatalı para birimi,
- refund bilgisinin farklı sistemde tutulması,
- farklı gelir tanımları,
- consent veya tagging eksikleri.

---

# 8. `purchase_day_distribution()` — churn eşiklerinin temel hazırlık analizi

```python
analysis.purchase_day_distribution()
```

Bu fonksiyonun amacı doğrudan churn hesaplamak değildir. Önce tekrar alışveriş davranışının zaman yapısını ortaya çıkarır.

Ana soru şudur:

> Aynı `user_id` bir satın alma yaptıktan sonra bir sonraki satın almayı genellikle kaç gün sonra yapmaktadır?

## 8.1 Hesaplama mantığı

Her kullanıcı için farklı satın alma günleri sıralanır.

Örnek kullanıcı A:

```text
5 Ocak
20 Ocak
18 Şubat
```

Aralıklar:

```text
5 Ocak → 20 Ocak  = 15 gün
20 Ocak → 18 Şubat = 29 gün
```

Örnek kullanıcı B:

```text
10 Mart
10 Mart
25 Nisan
```

Aynı gün içindeki iki satın alma, gün aralığı analizinde tek gün kabul edilir. Bu nedenle yalnızca:

```text
10 Mart → 25 Nisan = 46 gün
```

aralığı oluşur.

Bu yaklaşım, aynı gün içinde birden fazla sipariş verilmesinin satın alma süresi dağılımını sıfır günlük aralıklarla bozmasını engeller.

---

# 9. Gap observations neden kullanıcı sayısından farklıdır?

`Gap observations`, hesaplanan toplam ardışık satın alma aralığı sayısıdır.

Bir kullanıcı 2 farklı günde alışveriş yaptıysa 1 aralık üretir.

Bir kullanıcı 5 farklı günde alışveriş yaptıysa 4 aralık üretir.

Örnek:

```text
Repeat purchasers = 10.000
Gap observations  = 28.500
```

Bu normaldir. Bazı kullanıcılar birden çok satın alma aralığı üretmiştir.

Bu nedenle dağılımdaki yüzdeler kullanıcı yüzdesi olarak değil, **satın alma aralıklarının yüzdesi** olarak yorumlanmalıdır.

---

# 10. Ortalama ve median birlikte nasıl incelenir?

## Ortalama

Bütün satın alma aralıklarının aritmetik ortalamasıdır.

Örnek:

```text
12, 16, 18, 21, 190
```

Ortalama uzun 190 günlük aralık nedeniyle belirgin biçimde yükselir.

## Median / P50

Sıralanmış değerlerin ortasındaki değerdir. Uzun uç değerlerden ortalamaya göre daha az etkilenir.

Örnek çıktı:

```text
Mean   = 58 gün
Median = 31 gün
```

Bu fark, dağılımda uzun bekleme süreleri bulunduğunu düşündürür.

Bu durumda `58 gün` doğrudan churn sınırı olarak alınmamalıdır. Ortalama, az sayıdaki uzun aralık nedeniyle yukarı çekilmiş olabilir.

Başka bir örnek:

```text
Mean   = 34 gün
Median = 31 gün
```

Ortalama ile median birbirine yakınsa dağılımın merkezi daha dengeli olabilir.

---

# 11. P25, P75, P90 ve P95 nasıl yorumlanır?

Yüzdelikler, satın alma aralıklarının dağılımında belirli noktaları gösterir.

Örnek:

```text
P25 = 17 gün
P50 = 29 gün
P75 = 48 gün
P90 = 82 gün
P95 = 121 gün
```

Bu çıktı şu şekilde okunur:

```text
Aralıkların yaklaşık %25'i 17 gün veya daha kısa.
Aralıkların yaklaşık %50'si 29 gün veya daha kısa.
Aralıkların yaklaşık %75'i 48 gün veya daha kısa.
Aralıkların yaklaşık %90'ı 82 gün veya daha kısa.
Aralıkların yaklaşık %95'i 121 gün veya daha kısa.
```

Bu değerler churn eşiklerinin seçimi için en önemli referanslardan biridir.

### Neden P90 ve P95 özellikle önemlidir?

Churn tanımı genellikle normal tekrar satın alma davranışının dışına çıkan kullanıcıları ayırmak ister.

P90 = 82 gün ise gözlenen satın alma aralıklarının yalnızca yaklaşık %10'u 82 günden uzundur.

Bu nedenle 80–90 gün bandı churn için incelenebilecek aday bölgelerden biri olabilir.

Ancak P90 otomatik olarak doğru churn threshold değildir. İş modelinin doğal satın alma döngüsü ayrıca değerlendirilmelidir.

---

# 12. IQR ne gösterir?

IQR şu şekilde hesaplanır:

```text
IQR = P75 - P25
```

Örnek:

```text
P25 = 20
P75 = 50
IQR = 30 gün
```

Orta %50'lik satın alma aralıklarının 30 günlük bir banda yayıldığını gösterir.

İkinci örnek:

```text
P25 = 10
P75 = 120
IQR = 110 gün
```

Bu durumda kullanıcı davranışı çok daha dağınıktır. Bazı kullanıcılar çok hızlı, bazıları çok geç tekrar alışveriş yapmaktadır.

Geniş IQR varsa tek bir pre-churn ve churn sınırı bütün müşteri gruplarına eşit derecede uygun olmayabilir. Böyle bir durumda ileriki sürümlerde kategori, müşteri tipi veya satın alma sıklığına göre ayrı eşikler düşünmek daha doğru olabilir.

---

# 13. Standart sapma ve değişkenlik katsayısı nasıl kullanılır?

Standart sapma satın alma aralıklarının ne kadar dağıldığını gösterir.

Değişkenlik katsayısı ise standart sapmayı ortalamaya oranlar:

```text
CV = standart sapma / ortalama
```

Pratik okuma:

```text
CV < 0,5    → satın alma aralıkları görece düzenli
0,5–1,0     → orta düzey değişkenlik
CV >= 1,0   → satın alma aralıkları oldukça değişken
```

Bu aralıklar kesin istatistiksel kurallar değildir. Yalnızca tek bir churn eşiğinin ne kadar güvenli kullanılabileceğine dair yardımcı göstergelerdir.

Örnek:

```text
Median = 28 gün
P90    = 75 gün
CV     = 0,42
```

Bu yapı görece düzenli tekrar satın alma davranışına işaret edebilir.

Başka bir örnek:

```text
Median = 27 gün
P90    = 190 gün
CV     = 1,45
```

Median benzer görünse de kullanıcıların önemli bir kısmı çok farklı satın alma döngülerine sahiptir. Tek bir global eşik daha dikkatli değerlendirilmelidir.

---

# 14. Purchase-gap histogram nasıl incelenmelidir?

Histogram satın alma aralıklarını şu gün gruplarında gösterir:

```text
0–7
8–14
15–30
31–60
61–90
91–180
181–365
366+
```

Bu grafik yüzdeliklerin arkasındaki dağılım şeklini görmeyi sağlar.

## Örnek A — belirgin kısa satın alma döngüsü

```text
0–7       düşük
8–14      orta
15–30     çok yüksek
31–60     yüksek
61–90     düşük
91+       çok düşük
```

Bu görünümde kullanıcıların büyük kısmı ilk 60 gün içinde tekrar satın almaktadır. Pre-churn eşiği 45–60 gün bandında, churn eşiği 75–90 gün bandında test edilebilir.

## Örnek B — iki farklı kullanıcı davranışı

```text
15–30     yüksek
31–60     düşük
91–180    yeniden yüksek
```

Dağılım iki ayrı tepe gösteriyorsa tek tip satın alma döngüsü olmadığı düşünülebilir. Örneğin:

- sık alınan tüketim ürünü müşterileri,
- daha seyrek alınan yüksek fiyatlı ürün müşterileri

aynı veri içinde bulunabilir.

Bu durumda tek eşik kullanılmadan önce kategori veya müşteri tipi kırılımı incelenmelidir.

## Örnek C — uzun kuyruk

İlk 30–60 günde yoğunluk yüksek olduğu halde 181–365 ve 366+ gruplarında da kayda değer gözlem varsa dağılım uzun kuyrukludur.

Bu durum şunlardan kaynaklanabilir:

- mevsimsellik,
- kampanya dönemleri,
- uzun ürün yenileme süresi,
- çok farklı müşteri tipleri,
- çok uzun veri geçmişi.

Histogramdaki en yüksek bar doğrudan churn eşiği olarak seçilmemelidir.

---

# 15. Cumulative repeat-purchase coverage nasıl okunmalıdır?

Bu grafik şu soruya cevap verir:

> Gözlenen satın alma aralıklarının yüzde kaçı belirli gün sınırının içinde kalmaktadır?

Örnek:

```text
30 gün  → %42
45 gün  → %61
60 gün  → %74
90 gün  → %89
120 gün → %94
180 gün → %98
```

Bu durumda:

- aralıkların %74'ü 60 gün veya daha kısa,
- %89'u 90 gün veya daha kısa,
- %94'ü 120 gün veya daha kısadır.

Bu çıktı pre-churn ve churn sınırları için doğrudan referans sağlar.

Örneğin:

```text
Pre-churn threshold = 60 gün
Churn threshold     = 90 gün
```

seçilirse normal satın alma aralıklarının yaklaşık %74'ü pre-churn başlangıcından önce gerçekleşmiş, yaklaşık %89'u churn sınırından önce gerçekleşmiş olur.

Ancak coverage kullanıcı yüzdesi değildir. Satın alma aralıklarının yüzdesidir.

---

# 16. Pre-churn ve churn threshold nasıl seçilmelidir?

Eşik seçimi yalnızca tek bir metriğe bakılarak yapılmamalıdır. En sağlıklı yaklaşım birkaç göstergenin birlikte değerlendirilmesidir.

## Adım 1 — veri geçmişinin yeterli olup olmadığı kontrol edilir

Churn eşiği 120 gün olarak test edilecekse veri geçmişinin 120 günden belirgin biçimde uzun olması gerekir.

Örneğin sadece son 90 günlük veri varsa 120 günlük churn analizi güvenilir değildir.

Pratik olarak seçilen churn gününden daha uzun bir gözlem penceresi bulunmalıdır. Tekrar davranışının görülebilmesi için tercihen birkaç satın alma döngüsü kapsanmalıdır.

## Adım 2 — median ve P75 ile normal tekrar davranışı anlaşılır

Median ve P75, kullanıcıların büyük bölümünün ne kadar sürede tekrar alışveriş yaptığını gösterir.

Örnek:

```text
Median = 28 gün
P75    = 50 gün
```

Bu durumda 50 güne kadar olan süre hâlâ yaygın tekrar satın alma davranışı içinde sayılabilir.

Pre-churn eşiğini doğrudan 30 gün seçmek fazla erken olabilir; çünkü kullanıcıların yarısından fazlası zaten 28 gün civarında dönmektedir ve önemli bir bölümü 50 güne kadar normal davranış göstermektedir.

## Adım 3 — P90 ve P95 ile üst sınır davranışı incelenir

Örnek:

```text
P90 = 84 gün
P95 = 126 gün
```

Bu durumda 90 günlük churn eşiği normal tekrar satın alma davranışının üst tarafına yakın bir noktadadır.

120 günlük churn eşiği ise daha temkinli bir churn tanımı oluşturur.

## Adım 4 — coverage grafiği ile aday eşikler test edilir

Örnek:

```text
60 gün coverage  = %76
75 gün coverage  = %84
90 gün coverage  = %90
120 gün coverage = %95
```

Bu çıktıda örnek adaylar şöyle olabilir:

```text
Pre-churn = 60 veya 75 gün
Churn     = 90 veya 120 gün
```

Bu yalnızca başlangıç adaylarıdır. İş modeli kontrolü yapılmadan kesinleştirilmemelidir.

## Adım 5 — işin doğal satın alma döngüsü kontrol edilir

Aynı yüzdelik değerler farklı sektörlerde farklı anlam taşır.

### Hızlı tüketim örneği

Bir ürün normalde 20–30 günde yeniden alınması gereken bir ürünse:

```text
Median = 24
P75 = 35
P90 = 52
```

gibi bir yapıda:

```text
Pre-churn = 35–45 gün
Churn = 55–70 gün
```

adayları incelenebilir.

### Moda / dönemsel alışveriş örneği

Müşterilerin doğal olarak daha seyrek alışveriş yaptığı bir kategoride:

```text
Median = 52
P75 = 95
P90 = 160
```

60 günlük churn eşiği çok agresif olabilir. Bu yapı için daha uzun eşikler gerekebilir.

### Yıllık veya mevsimsel alışveriş örneği

Yılda bir kez satın alınan ürünlerde standart gün bazlı churn yaklaşımı tek başına anlamlı olmayabilir. Bir önceki yılın aynı dönemine dönüş, sezon veya üyelik yenileme tarihi ayrıca değerlendirilmelidir.

---

# 17. Pre-churn threshold seçerken temel mantık

Pre-churn, henüz churn olmamış ancak normal geri dönüş davranışının dışına çıkmaya başlayan kullanıcıları işaretlemek için kullanılır.

Bu nedenle pre-churn eşiğinin amacı churn eşiğinden önce aksiyon alınabilecek bir alan oluşturmaktır.

Örnek:

```text
Median = 30
P75 = 52
P90 = 88
P95 = 130
```

Olası tanım:

```text
Pre-churn threshold = 60 gün
Churn threshold = 90 gün
```

Bu seçimde:

```text
0–60 gün  → normal/aktif alan
61–90 gün → normal davranışın üst tarafına çıkmış, müdahale edilebilir alan
90+ gün   → churn alanı
```

Başka bir senaryoda kullanıcıların %85'i 45 gün içinde tekrar satın alıyorsa pre-churn 60 gün yerine 45–50 gün civarında daha anlamlı olabilir.

Pre-churn için tek bir evrensel formül yoktur. Ama genel amaç churn sınırından önce, iş açısından aksiyon alınabilecek yeterli zaman bırakmaktır.

---

# 18. Churn threshold seçerken temel mantık

Churn eşiği, kullanıcının normal tekrar satın alma davranışından yeterince uzaklaştığı noktayı temsil etmelidir.

Aşağıdaki göstergeler birlikte incelenmelidir:

- P90,
- P95,
- cumulative coverage,
- histogramın uzun kuyruğu,
- ürün yenileme süresi,
- kampanya ve sezon etkisi,
- müşteri segmentleri,
- seçilen eşiğin CRM veya pazarlama kullanım amacı.

Örnek:

```text
P75 = 50
P90 = 85
P95 = 125
90 günlük coverage = %91
```

90 günlük churn eşiği makul bir başlangıç adayı olabilir.

Ancak marka, müşterilerin 3–4 ayda bir alışveriş yapmasının normal olduğunu biliyorsa 90 gün fazla kısa kalabilir. İş bilgisi istatistiksel dağılımın önüne geçebilir.

---

# 19. Üç farklı threshold örneği

## Senaryo 1 — düzenli tekrar satın alma

```text
Median = 25
P75 = 40
P90 = 62
P95 = 80
CV = 0,45
```

Dağılım görece düzenlidir.

Aday yaklaşım:

```text
Pre-churn = 45–50
Churn = 70–80
```

## Senaryo 2 — orta düzey değişkenlik

```text
Median = 32
P75 = 60
P90 = 95
P95 = 145
CV = 0,85
```

Aday yaklaşım:

```text
Pre-churn = 60–75
Churn = 100–120
```

Duyarlılık analizi özellikle önemlidir.

## Senaryo 3 — çok dağınık davranış

```text
Median = 30
P75 = 95
P90 = 220
P95 = 340
CV = 1,60
```

Tek global eşik risklidir. Önce aşağıdaki kırılımlar önerilir:

- ürün kategorisi,
- müşteri tipi,
- satın alma sıklığı,
- gelir seviyesi,
- ilk satın alma kanalı,
- coğrafi veya kampanya grubu.

---

# 20. `churn_analysis(pre_churn_threshold, churn_threshold)`

Örnek:

```python
analysis.churn_analysis(60, 90)
```

Kurallar:

```text
purchase_count = 0
→ never_purchased

purchase_count > 0
ve days_since_last_purchase <= 60
→ active_purchaser

purchase_count > 0
ve 60 < days_since_last_purchase <= 90
→ pre_churn

purchase_count > 0
ve days_since_last_purchase > 90
→ churned
```

`pre_churn_threshold`, `churn_threshold` değerinden küçük olmalıdır.

---

# 21. Pre-churn rate ve churn rate nasıl hesaplanır?

Her iki oranın paydası alışveriş yapan kullanıcı kitlesidir.

## Pre-churn rate

```text
pre_churn kullanıcı / tüm purchasers
```

## Churn rate

```text
churned kullanıcı / tüm purchasers
```

Örnek:

```text
Purchasers = 100.000
Active = 55.000
Pre-churn = 18.000
Churned = 27.000
```

Sonuç:

```text
Pre-churn rate = %18
Churn rate = %27
```

Hiç satın alma yapmamış kullanıcılar bu oranlara dahil edilmez.

---

# 22. Active / Pre-churn / Churned dağılımı nasıl yorumlanır?

Örnek A:

```text
Active    = %68
Pre-churn = %8
Churned   = %24
```

Pre-churn havuzu görece küçüktür. Churn zaten yüksekse müdahale geç kalıyor olabilir veya churn eşiği uzun tutulmuş olabilir.

Örnek B:

```text
Active    = %45
Pre-churn = %30
Churned   = %25
```

Kullanıcıların önemli bölümü pre-churn alanındadır. Yakın dönemde churn oranını artırabilecek büyük bir risk havuzu bulunduğu düşünülebilir.

Örnek C:

```text
Active    = %80
Pre-churn = %15
Churned   = %5
```

Bu sonuç güçlü geri dönüş davranışına işaret edebilir. Ancak churn eşiğinin gereğinden uzun seçilip seçilmediği ayrıca kontrol edilmelidir.

---

# 23. One-time ve repeat kullanıcılar neden ayrı incelenmelidir?

Pre-churn ve churn çıktılarında tek alışveriş yapanlarla tekrar alışveriş yapan kullanıcılar farklı anlam taşır.

## Churned one-time buyers

İlk alışverişten sonra ikinci alışverişe hiç geçememiş ve churn sınırını aşmış kullanıcılardır.

Bu grup için problem genellikle ilk alışveriş sonrası devamlılık olabilir.

## Churned repeat buyers

Geçmişte birden fazla satın alma yapmış, ancak daha sonra churn sınırını aşmış kullanıcılardır.

Bu grup daha önce alışkanlık veya bağlılık göstermiştir. Geri kazanım açısından ayrı değerlendirilmesi daha anlamlı olabilir.

Örnek:

```text
Churned users = 30.000
Churned one-time = 22.000
Churned repeat = 8.000
```

Churn kitlesinin çoğu tek alışveriş yapanlardan oluşuyorsa öncelik ikinci alışverişi artıran stratejilere verilebilir.

---

# 24. Pre-churn ve churn gelir payları nasıl yorumlanır?

## Pre-churn revenue share

Pre-churn kullanıcıların geçmişte ürettiği gelirin bütün purchasers gelirine oranıdır.

## Churned revenue share

Churn olmuş kullanıcıların geçmişte ürettiği gelirin bütün purchasers gelirine oranıdır.

Örnek:

```text
Pre-churn rate = %15
Pre-churn revenue share = %28
```

Pre-churn kullanıcılar sayı olarak %15 iken geçmiş gelirin %28'ini oluşturuyorsa bu kitlenin ortalama değeri daha yüksek olabilir.

Başka bir örnek:

```text
Churn rate = %30
Churned revenue share = %12
```

Churn olan kullanıcı sayısı yüksek olsa da bu grubun geçmiş gelir katkısı düşük olabilir. Churn kitlesi büyük ölçüde düşük değerli veya tek seferlik kullanıcılardan oluşuyor olabilir.

Bu metrikler **kaybedilen gelir** değildir. Gelecekte kaybedilecek geliri tahmin etmez. Sadece mevcut grupların geçmiş gelir katkısını gösterir.

---

# 25. Status diagnostics tablosu nasıl incelenir?

Tablo active, pre-churn ve churned kullanıcıları aşağıdaki alanlarda karşılaştırır:

- kullanıcı sayısı,
- ortalama satın alma sayısı,
- ortanca satın alma sayısı,
- ortalama gelir,
- ortanca gelir,
- son satın almadan geçen ortalama gün,
- son satın almadan geçen ortanca gün.

Örnek:

```text
                 Avg purchases   Avg revenue
Active                4,8            1.250
Pre-churn             3,9            1.480
Churned               1,7              410
```

Pre-churn grubunun ortalama gelirinin active gruptan yüksek olması, değerli müşterilerin bir bölümünün risk alanına geçtiğini gösterebilir.

Başka bir örnek:

```text
Active avg revenue  = 900
Active median revenue = 240
```

Ortalama ile ortanca arasındaki büyük fark, az sayıdaki yüksek gelirli kullanıcının ortalamayı yukarı çektiğini gösterir. Bu nedenle gelir karşılaştırmasında ortalama ve median birlikte değerlendirilmelidir.

---

# 26. Purchase frequency bazında pre-churn ve churn nasıl yorumlanır?

Kullanıcılar toplam satın alma sayılarına göre gruplandırılır:

```text
1 purchase
2 purchases
3–5 purchases
6+ purchases
```

Her grupta pre-churn ve churn oranları ayrı hesaplanır.

Örnek:

```text
                 Pre-churn   Churn
1 purchase          %18       %44
2 purchases         %16       %29
3–5 purchases       %12       %17
6+ purchases         %8        %7
```

Bu tablo, satın alma sayısı arttıkça churn oranının düştüğünü gösterebilir.

Ancak bu ilişki nedensellik değildir. “Daha fazla satın alma yaptırmak churnü otomatik düşürür” sonucu çıkarılmamalıdır.

İş açısından şu sorular incelenebilir:

- Churn sorunu özellikle tek alışveriş yapanlarda mı yoğun?
- İkinci satın alma kritik bir eşik mi?
- 6+ purchase kitlesinde pre-churn oranı yükseliyor mu?
- Çok değerli tekrar müşterilerinin risk alanına girmesi ayrı kampanya gerektiriyor mu?

---

# 27. Churn threshold sensitivity nasıl yorumlanır?

Araç, seçilen churn gününün çevresindeki alternatif eşiklerde churn oranını yeniden hesaplar.

Örnek:

```text
60 gün  → %39
75 gün  → %33
90 gün  → %28
105 gün → %25
120 gün → %22
150 gün → %18
```

Bu grafik şu soruya cevap verir:

> Churn oranı seçilen gün sınırına ne kadar bağlıdır?

## Stabil örnek

```text
75 gün  → %29
90 gün  → %28
105 gün → %27
```

Sonuç eşik değişimine çok hassas değildir.

## Hassas örnek

```text
75 gün  → %41
90 gün  → %28
105 gün → %18
```

Küçük gün değişiklikleri churn oranını ciddi biçimde değiştiriyorsa tek bir churn oranını kesin gerçek gibi sunmak doğru değildir.

Raporlama örneği:

> 90 günlük churn tanımında churn oranı %28'dir. Eşik 75 güne indirildiğinde %41, 105 güne çıkarıldığında %18 olmaktadır.

---

# 28. Pre-churn ve churn gap coverage nasıl yorumlanır?

Analiz iki ayrı kapsama değeri üretir:

```text
pre_churn_gap_coverage
churn_gap_coverage
```

Örnek:

```text
Pre-churn threshold = 60
Pre-churn gap coverage = %74

Churn threshold = 90
Churn gap coverage = %90
```

Bu şu anlama gelir:

- gözlenen tekrar satın alma aralıklarının %74'ü 60 gün veya daha kısa,
- %90'ı 90 gün veya daha kısadır.

Bu yapı, 60–90 gün arasını pre-churn alanı olarak kullanmanın geçmiş davranışla uyumunu kontrol etmeye yardımcı olur.

---

# 29. Eşik seçiminde önerilen karar süreci

Tek bir otomatik formül yerine aşağıdaki sıra önerilir:

```text
1. Veri tarihçesi ve purchase tracking kontrol edilir
2. Median, P75, P90 ve P95 incelenir
3. Histogramın şekli kontrol edilir
4. Cumulative coverage incelenir
5. Pre-churn için ilk aday oluşturulur
6. Churn için ilk aday oluşturulur
7. Ürün/kategori satın alma döngüsü ile karşılaştırılır
8. Churn sensitivity grafiği kontrol edilir
9. One-time ve repeat kullanıcı sonuçları karşılaştırılır
10. İlk kullanım sonrası eşikler periyodik olarak yeniden değerlendirilir
```

Eşikler bir defa belirlenip sonsuza kadar sabit bırakılmamalıdır. Kullanıcı davranışı, fiyat, kampanya sıklığı, ürün yapısı ve sezon değiştikçe satın alma döngüsü de değişebilir.

---

# 30. HTML dashboard nasıl kullanılmalıdır?

`churn_analysis()` çalıştıktan sonra:

```text
ga4_churn_dashboard.html
```

oluşturulur.

Dashboard hızlı paylaşım için özet görünüm sağlar. Ana kullanım alanları:

- active / pre-churn / churned kullanıcı hacmini göstermek,
- pre-churn ve churn oranlarını raporlamak,
- durum gruplarının satın alma ve gelir seviyelerini karşılaştırmak,
- analizin hangi eşiklerle üretildiğini açık biçimde göstermek.

Dashboard yeni bir hesaplama yapmaz. Notebook ve BigQuery tablolarındaki sonuçların sunum katmanıdır.

---

# 31. Analiz hangi durumlarda yanıltıcı olabilir?

## `user_id` kapsamı düşükse

GA4 kullanıcılarının yalnızca küçük bölümünde `user_id` varsa sonuç bütün kullanıcı tabanını temsil etmez.

## Purchase tracking hatalıysa

Duplicate veya eksik purchase event'leri satın alma sayısını, gelir değerini ve satın alma aralıklarını doğrudan bozar.

## Veri geçmişi kısa ise

90 günlük veride 180 günlük churn tanımı üretmek mantıklı değildir.

## Sezonluk iş modeli varsa

Yaz tatili, okul dönemi, Black Friday, Ramazan, yılbaşı veya yıllık yenileme gibi dönemler satın alma aralıklarını ciddi biçimde değiştirebilir.

## Çok farklı ürün döngüleri aynı analizdeyse

Gıda ürünü ve dayanıklı tüketim ürünü aynı marka altında analiz ediliyorsa tek churn eşiği iki müşteri davranışını iyi temsil etmeyebilir.

## Active etiketi yanlış anlaşılırsa

`active_purchaser` kullanıcının gelecekte kesinlikle tekrar alışveriş yapacağı anlamına gelmez. Yalnızca henüz pre-churn sınırını aşmadığını gösterir.

## Pre-churn etiketi tahmin olarak yorumlanırsa

`pre_churn`, “bu kullanıcı kesin churn olacak” anlamına gelmez. Sadece son satın almadan geçen süreye göre tanımlanan risk bölgesidir.

---

# 32. Sonuçların yönetime sunulması için örnek

Zayıf anlatım:

```text
Churn oranı %27.
```

Daha açıklayıcı anlatım:

```text
Analiz, GA4'te user_id bulunan 82.000 satın alma yapmış kullanıcı üzerinden hesaplanmıştır.

Tekrar satın alma aralıklarının medianı 31 gün, P90 değeri 86 gündür.
60 gün pre-churn, 90 gün churn eşiği seçilmiştir.

Bu tanımda:
- %56 active,
- %17 pre-churn,
- %27 churned durumundadır.

Pre-churn kullanıcılar geçmiş purchaser gelirinin %24'ünü oluşturmaktadır.
Tek alışveriş yapan kullanıcıların churn oranı %46 iken 6+ alışveriş yapanlarda %9'dur.

Churn eşiği 75 güne çekildiğinde oran %34'e, 105 güne çıkarıldığında %22'ye değişmektedir.
```

Bu format hem sonucu hem de sonucun hangi varsayımla üretildiğini görünür hale getirir.

---

# 33. Analiz öncesi ve sonrası kontrol listesi

- [ ] `user_id` implementasyonu yeterli kapsama sahip mi?
- [ ] Kaynak dataset doğru mu?
- [ ] Kaynak tablonun son tarihi güncel mi?
- [ ] `purchase` event'i doğru çalışıyor mu?
- [ ] Duplicate purchase kontrolü yapıldı mı?
- [ ] Revenue değerleri güvenilir mi?
- [ ] Veri geçmişi seçilecek churn gününden yeterince uzun mu?
- [ ] Median ve P75 kontrol edildi mi?
- [ ] P90 ve P95 kontrol edildi mi?
- [ ] Histogram incelendi mi?
- [ ] Cumulative coverage incelendi mi?
- [ ] Pre-churn eşiği iş açısından aksiyon alınabilecek bir pencere bırakıyor mu?
- [ ] Churn eşiği normal tekrar satın alma davranışının yeterince dışında mı?
- [ ] Threshold sensitivity incelendi mi?
- [ ] One-time ve repeat kullanıcılar ayrı yorumlandı mı?
- [ ] Pre-churn ve churn revenue share “kaybedilen gelir” olarak adlandırılmadı mı?
- [ ] Sonuçların yalnızca `user_id` bulunan kullanıcıları kapsadığı raporda belirtildi mi?

---

# 34. Kısa özet

Analizin temel yaklaşımı şu sırayı izler:

```text
GA4 user_id bulunan kullanıcıları al
        ↓
Her kullanıcı için satın alma geçmişini özetle
        ↓
Tekrar satın alma gün aralıklarını hesapla
        ↓
Median / P75 / P90 / P95 ve dağılımı incele
        ↓
Pre-churn ve churn için aday günler belirle
        ↓
İş modelinin doğal satın alma döngüsü ile karşılaştır
        ↓
Active / pre-churn / churned sınıflarını oluştur
        ↓
Satın alma sıklığı ve gelir farklarını incele
        ↓
Threshold sensitivity ile sonucun sağlamlığını kontrol et
```

Bu çalışmada churn oranı tek başına nihai sonuç değildir. En doğru yorum; satın alma aralıkları, seçilen pre-churn ve churn eşikleri, kullanıcı değerleri ve duyarlılık analizi birlikte değerlendirilerek yapılır.
