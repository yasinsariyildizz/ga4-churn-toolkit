# GA4 Churn Toolkit — Analiz ve Yorumlama Rehberi (TR)

Bu doküman, `ga4-churn-toolkit` içindeki **basic purchase-based churn** analizinin nasıl çalıştığını, üretilen metriklerin ve grafiklerin ne anlama geldiğini ve sonuçların nasıl yorumlanması gerektiğini açıklar.

> Bu sürüm özellikle basit tutulmuştur. Amaç, GA4 BigQuery export verisi üzerinden anlaşılır ve tekrar kullanılabilir bir churn analizi sağlamaktır. Bu araç churn'ü tahmin etmez; seçilen bir hareketsizlik eşiğine göre **mevcut kullanıcıları sınıflandırır**.

---

## 1. Analizin temel fikri

Analiz purchase davranışına dayanır.

Bir kullanıcı en az bir kez `purchase` event'i oluşturmuşsa **purchaser** kabul edilir. Kullanıcının son purchase tarihinden analiz tarihine kadar geçen süre hesaplanır:

```text
days_since_last_purchase = analysis_date - last_purchase_date
```

Churn analizi çalıştırılırken bir eşik verilir:

```python
analysis.churn_analysis(90)
```

Bu örnekte 90 gün eşiktir.

Sınıflandırma:

```text
purchase_count = 0
→ never_purchased

purchase_count > 0 ve days_since_last_purchase <= threshold
→ active_purchaser

purchase_count > 0 ve days_since_last_purchase > threshold
→ churned
```

### Analiz tarihi nedir?

Kullanıcı ayrıca bir analiz tarihi girmez. Araç kaynak veride bulunan en güncel `event_date` değerini kullanır:

```text
analysis_date = MAX(event_date)
```

Bu nedenle sonuçlar, dataset'in ne kadar güncel olduğuna bağlıdır. Dataset eskiyse churn sonucu da o eski tarihe göre hesaplanır.

---

## 2. Kullanıcıdan alınan inputlar

```python
analysis = ChurnAnalysis(
    project_id="your-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

| Input | Açıklama |
|---|---|
| `project_id` | GA4 export verisinin bulunduğu GCP projesi |
| `dataset_id` | GA4 BigQuery export dataset'i |
| `table_id` | Kaynak tablo veya wildcard, örn. `events_*` |
| `output_dataset_id` | Analiz tablolarının yazılacağı dataset |

Churn threshold burada verilmez. Eşik yalnızca `churn_analysis()` fonksiyonunda girilir.

---

# 3. Önerilen çalışma sırası

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

Bu sıra önemlidir. Her adım bir sonraki adımın yorumlanmasını kolaylaştırır.

---

# 4. `dry_run()` — Maliyet ve tarama kontrolü

```python
analysis.dry_run()
```

Bu fonksiyon sorguları çalıştırmadan önce yaklaşık ne kadar verinin taranacağını kontrol eder.

Ana çıktı:

```text
Estimated scan: X GB
```

## Nasıl yorumlanır?

Bu değer analiz sonucu değildir. Yalnızca BigQuery sorgularının okuyacağı yaklaşık veri miktarını gösterir.

Özellikle:

```python
table_id="events_*"
```

kullanılıyorsa tüm eşleşen tablolar taranabilir. Büyük GA4 export dataset'lerinde bu yüksek maliyet yaratabilir.

### Ne zaman dikkat edilmeli?

- Beklenenden çok daha yüksek GB/TB görünüyorsa
- Yanlış dataset veya wildcard seçilmişse
- Test için tüm tarihçeyi taramaya gerek yoksa

Bu fonksiyon bir **güvenlik ve maliyet kontrol adımıdır**, analitik yorum üretmez.

---

# 5. `create_base_table()` — Kullanıcı seviyesinde temel tablo

```python
analysis.create_base_table()
```

Bu adımın grain'i:

```text
1 satır = 1 user_pseudo_id
```

Ana çıktı tablosu:

```text
<output_dataset>.churn_base
```

## Temel kolonlar

| Kolon | Anlamı |
|---|---|
| `user_pseudo_id` | GA4 cihaz/tarayıcı bazlı kullanıcı tanımlayıcısı |
| `first_event_date` | Kullanıcının dataset içindeki ilk event tarihi |
| `last_event_date` | Kullanıcının son event tarihi |
| `event_count` | Kullanıcının toplam event sayısı |
| `session_count` | Kullanıcının distinct `ga_session_id` sayısı |
| `purchase_count` | `purchase` event sayısı |
| `revenue` | Purchase event'lerindeki toplam `ecommerce.purchase_revenue` |
| `first_purchase_date` | İlk purchase tarihi |
| `last_purchase_date` | Son purchase tarihi |
| `analysis_date` | Kaynaktaki maksimum event tarihi |
| `days_since_last_purchase` | Son purchase'tan analiz tarihine geçen gün |

## Notebook KPI'ları

### Users

Dataset içindeki distinct `user_pseudo_id` sayısıdır.

### Purchasers

En az bir purchase event'i olan kullanıcı sayısıdır.

### One-time purchasers

Sadece bir purchase event'i olan kullanıcı sayısıdır.

Bu grup churn analizinde özellikle önemlidir; tek sefer alışveriş yapan kullanıcılar genellikle repeat müşterilerden farklı davranır.

### Repeat purchasers

Birden fazla purchase event'i olan kullanıcı sayısıdır.

### Purchaser rate

```text
purchasers / all users
```

Bu metrik churn oranı değildir. Trafiğin ne kadarının purchaser'a dönüştüğünü gösteren basit bir kullanıcı payıdır.

### Repeat rate

```text
repeat purchasers / purchasers
```

Purchaser tabanının ne kadarının tekrar satın alma davranışı gösterdiğini anlatır.

### Revenue

Dataset içindeki purchase event'lerinin toplam historical revenue değeridir.

> Bu değer muhasebe geliri olmak zorunda değildir. GA4 tracking doğruluğu, currency implementasyonu ve duplicate purchase event'leri sonucu etkileyebilir.

---

# 6. `purchase_day_distribution()` — Satın alma aralıklarının analizi

```python
analysis.purchase_day_distribution()
```

Bu adım churn threshold seçmeden önce müşteri satın alma ritmini anlamak için kullanılır.

## Hesaplama mantığı

Her kullanıcı için distinct purchase günleri sıralanır.

Örnek:

```text
10 Ocak
25 Ocak
20 Şubat
```

Gap'ler:

```text
15 gün
26 gün
```

Aynı gün içinde iki purchase varsa aynı gün iki ayrı purchase günü olarak sayılmaz. Böylece sıfır günlük interval'ların dağılımı bozması engellenir.

> Buradaki analiz yalnızca en az iki farklı purchase gününe sahip kullanıcılar hakkında bilgi verir. One-time purchaser'lar gap distribution'a dahil değildir.

---

## 6.1 Gap Observations

Toplam gözlenen ardışık purchase interval sayısıdır.

Örneğin bir kullanıcı 5 farklı günde purchase yaptıysa 4 gap üretir.

Bu nedenle:

```text
gap observations != repeat purchaser count
```

olması normaldir.

---

## 6.2 Mean Gap

Purchase interval'larının aritmetik ortalamasıdır.

Uzun bekleme sürelerinden kolay etkilenir.

Örneğin gap'ler:

```text
10, 12, 14, 15, 180
```

ise mean oldukça yükselir.

Bu nedenle mean'i tek başına threshold seçmek için kullanmak doğru değildir.

---

## 6.3 Median / P50

Purchase interval'larının ortanca değeridir.

```text
Median = 30 gün
```

ise gözlenen gap'lerin yaklaşık yarısı 30 gün veya daha kısa, yarısı daha uzundur.

Median, uç değerlerden mean'e göre daha az etkilenir.

---

## 6.4 P25 ve P75

P25, gap'lerin %25'inin bu değerin altında/eşit olduğunu; P75 ise %75'inin altında/eşit olduğunu gösterir.

Örneğin:

```text
P25 = 18
P75 = 55
```

ise purchase interval'larının orta %50'lik bölümü yaklaşık 18–55 gün arasındadır.

---

## 6.5 IQR

```text
IQR = P75 - P25
```

Dağılımın orta %50'sinin ne kadar yayıldığını gösterir.

Düşük IQR → müşterilerin tekrar satın alma ritmi daha tutarlı olabilir.

Yüksek IQR → kullanıcı davranışı heterojendir; tek churn threshold tüm müşteriler için aynı derecede anlamlı olmayabilir.

---

## 6.6 P90 ve P95

Churn threshold tartışmasında en faydalı değerlerdendir.

Örnek:

```text
P90 = 82 gün
```

Bu, gözlenen repeat-purchase interval'larının yaklaşık %90'ının 82 gün veya daha kısa olduğunu ifade eder.

90 günlük churn threshold seçilirse bu eşik normal repeat davranışının oldukça üst tarafında kalıyor olabilir.

Ancak:

> P90 otomatik olarak “doğru churn threshold” değildir.

P90 yalnızca davranışsal referans noktasıdır. Sezonluk ürünler, uzun satın alma döngüsü, abonelik yapısı veya veri penceresi threshold yorumunu değiştirebilir.

---

## 6.7 Standard Deviation

Gap'lerin ortalama etrafındaki değişkenliğini ölçer.

Yüksek standart sapma, kullanıcıların satın alma aralıklarının birbirinden ciddi şekilde farklı olabileceğini gösterir.

---

## 6.8 Coefficient of Variation (CV)

```text
CV = standard deviation / mean
```

Farklı ölçeklerdeki dağılımların göreli değişkenliğini anlamak için kullanılır.

Kabaca:

```text
CV < 0.5   → daha konsantre davranış
0.5–1.0    → orta düzey değişkenlik
CV >= 1.0  → yüksek değişkenlik
```

Bu sınırlar evrensel kurallar değildir; sadece yorumlama yardımcılarıdır.

Yüksek CV varsa tek threshold kullanımına daha temkinli yaklaşılmalıdır.

---

# 7. Purchase-gap histogram nasıl okunur?

Grafik gap'leri bucket'lara ayırır:

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

Her bar o aralıkta kaç purchase interval gözlendiğini gösterir.

## Örnek yorum

Eğer en büyük bar:

```text
15–30 gün
```

ise repeat purchase davranışının yoğun bir kısmı bu aralıkta gerçekleşiyor olabilir.

Eğer 181+ bucket'larında da ciddi yoğunluk varsa:

- uzun satın alma döngüsü olabilir,
- müşteri segmentleri farklı davranıyor olabilir,
- sezonluk pattern olabilir,
- uzun veri geçmişi nedeniyle tail uzuyor olabilir.

### Histogramdan ne çıkarılmamalı?

“En yüksek bar 31–60, o halde churn threshold 60 gündür” sonucu otomatik çıkarılmamalıdır.

Histogram davranışın şeklini gösterir, churn için business kararını tek başına vermez.

---

# 8. Cumulative Repeat-Purchase Coverage grafiği

Bu grafik şu soruya cevap verir:

> Gözlenen repeat purchase interval'larının yüzde kaçı X gün içinde gerçekleşiyor?

Örnek:

```text
30 gün → %48
60 gün → %72
90 gün → %89
180 gün → %97
```

Yorum:

- Repeat purchase interval'larının %48'i 30 gün içinde
- %72'si 60 gün içinde
- %89'u 90 gün içinde gerçekleşmiş

Bu grafik churn threshold seçimi için histogramdan daha doğrudan bir referans sağlar.

Örneğin 90 günlük threshold kullanılıyorsa ve coverage %89 ise seçilen eşik gözlenen historical repeat interval'ların yaklaşık %89'unu kapsıyor demektir.

Bu yine “89% kullanıcı 90 günde döner” anlamına gelmez. Metric interval bazlıdır, kullanıcı bazlı değildir.

---

# 9. Otomatik Purchase Behavior Insights

Araç dağılım sonuçlarından açıklayıcı insight cümleleri üretir.

Örnek:

```text
The median repeat-purchase interval is 31 days.
The middle 50% of repeat-purchase intervals fall between 18 and 55 days.
The distribution is right-skewed.
Repurchase timing is highly variable.
```

Bu insight'lar deterministik özetlerdir; yapay zekâ tahmini değildir.

Amaç, analyst'in sayıları hızlı yorumlamasına yardımcı olmaktır.

---

# 10. `churn_analysis(threshold)`

Örnek:

```python
analysis.churn_analysis(90)
```

Bu adım verilen threshold'a göre purchaser'ları sınıflandırır.

## Churn rate formülü

```text
churn rate = churned purchasers / all purchasers
```

Never-purchased kullanıcılar denominator'a dahil edilmez.

Örnek:

```text
Total users        1,000,000
Purchasers           200,000
Churned               60,000

Churn Rate = 60,000 / 200,000 = 30%
```

Yanlış hesap:

```text
60,000 / 1,000,000
```

çünkü 800,000 never-purchased kullanıcı churn risk tabanına hiç girmemiştir.

---

# 11. Churn Analysis KPI'ları

## Purchasers

En az bir purchase yapan toplam kullanıcı sayısı.

## Active Purchasers

Son purchase'ı threshold içinde kalan purchaser'lar.

## Churned Users

Son purchase'ından beri geçen süre threshold'u aşan purchaser'lar.

## One-Time Purchasers

Sadece bir purchase yapmış purchaser'lar.

Bu segment churn sonuçlarında çok önemlidir; bir kez satın alıp geri dönmeyen kullanıcılar repeat purchaser'lardan farklı değerlendirilmelidir.

## Churned One-Time Buyers

Bir purchase yapmış ve threshold'u aşmış kullanıcılar.

## Churned Repeat Buyers

Birden fazla purchase yapmış ancak son purchase sonrası threshold'u aşmış kullanıcılar.

## Churned Revenue Share

```text
historical revenue of churned users
-----------------------------------
historical revenue of all purchasers
```

Bu metric:

> “Kaybettiğimiz revenue budur”

anlamına gelmez.

Bu kullanıcıların geçmişte ürettiği revenue payını gösterir. Future lost revenue tahmini değildir.

---

# 12. Status Diagnostics tablosu

Active purchaser, churned ve never-purchased grupları karşılaştırılır.

Kolonlar arasında:

- Users
- Avg purchases
- Median purchases
- Avg revenue
- Median revenue
- Avg inactive days

bulunur.

## Mean ve median neden birlikte gösteriliyor?

Revenue ve purchase count dağılımları genellikle sağa çarpıktır.

Örneğin:

```text
Active avg revenue   = 1,200
Active median revenue = 320
```

ise birkaç yüksek değerli kullanıcı ortalamayı yukarı çekiyor olabilir.

Bu nedenle mean'i median ile birlikte okumak gerekir.

---

# 13. Purchaser Status grafiği

Active ve churned purchaser sayısını karşılaştırır.

Bu grafik mutlak hacmi gösterir.

Örnek:

```text
Active   120,000
Churned   80,000
```

buradan churn rate yaklaşık %40 olarak düşünülebilir.

Ancak bar uzunluklarını tek başına değil, churn rate KPI ile birlikte değerlendirmek daha doğrudur.

---

# 14. Churn Rate by Purchase Frequency grafiği

Purchaser'lar şu segmentlere ayrılır:

```text
1 purchase
2 purchases
3–5 purchases
6+ purchases
```

Her segment için churn rate hesaplanır.

## Neden önemli?

Tek seferlik purchaser'lar ile güçlü repeat müşteriler aynı churn dinamiğine sahip olmayabilir.

Örnek:

```text
1 purchase   → %52 churn
2 purchases  → %31 churn
3–5          → %18 churn
6+           → %9 churn
```

Bu sonuç, purchase frequency arttıkça müşteri ilişkisinin daha dayanıklı olabileceğini düşündürebilir.

Ama bu korelasyon **nedensellik değildir**. “Daha çok purchase yaptırmak churn'ü otomatik olarak düşürür” sonucu bu analizden tek başına çıkarılamaz.

---

# 15. Threshold Sensitivity grafiği

Bu analiz en önemli kontrollerden biridir.

Örneğin seçilen threshold:

```text
90 gün
```

ise araç çevresindeki değerlerde churn rate'i tekrar hesaplar.

Örnek:

```text
60 gün  → %36
75 gün  → %31
90 gün  → %27
105 gün → %24
120 gün → %21
150 gün → %17
```

## Nasıl yorumlanır?

Threshold büyüdükçe churn olarak işaretlemek zorlaşır, bu nedenle churn rate genellikle düşer.

Grafik şu soruyu cevaplar:

> Sonuç seçtiğim threshold'a ne kadar hassas?

Eğer:

```text
75 gün = %30
90 gün = %29
105 gün = %28
```

ise sonuç görece stabil olabilir.

Ama:

```text
75 gün = %42
90 gün = %29
105 gün = %18
```

ise küçük threshold değişiklikleri sonucu ciddi etkiliyor demektir.

Bu durumda tek bir churn oranını kesin gerçek gibi sunmak doğru değildir.

---

# 16. Threshold Context / Gap Coverage

Churn ekranında seçilen threshold'un historical purchase-gap dağılımındaki karşılığı gösterilir.

Örneğin:

```text
Threshold = 90 gün
Gap coverage = %91
P90 = 86 gün
```

Bu, seçilen threshold'un historical repeat-purchase interval'larının yaklaşık %91'inden daha uzun/eşit olduğunu gösterir.

Bu davranışsal bir sanity check'tir.

---

# 17. Threshold nasıl seçilmeli?

Bu basic tool threshold'u otomatik belirlemez. Bunun nedeni churn tanımının business bağlamına bağlı olmasıdır.

Threshold belirlerken birlikte değerlendirilmesi gerekenler:

1. Median purchase gap
2. P75 / P90 / P95
3. Purchase-gap histogram
4. Cumulative coverage
5. Threshold sensitivity
6. Business purchase cycle
7. Seasonality
8. Ürün kategorisi
9. Veri geçmişinin uzunluğu

### Basit örnek yaklaşım

Diyelim:

```text
Median = 28
P75 = 48
P90 = 83
P95 = 125
```

Olası testler:

```text
60
90
120
```

olabilir.

Sonra sensitivity ve business anlamlılığı değerlendirilir.

> Araç P90'ı otomatik threshold olarak kabul etmez ve kabul etmemelidir. P90 yalnızca aday eşik oluşturmak için referans olabilir.

---

# 18. HTML Dashboard

`churn_analysis()` sonunda:

```text
ga4_churn_dashboard.html
```

oluşturulur.

Dashboard şu bölümleri içerir:

- Selected threshold
- Purchasers
- Active purchasers
- Churned users
- Churn rate
- Gap coverage
- Churned historical revenue share
- Analytical insights
- Status diagnostics
- Churn by purchase frequency
- Threshold sensitivity

Dashboard sonuçların paylaşılmasını kolaylaştırır; ancak dashboard içindeki sonuçların anlamı notebook çıktılarıyla aynıdır.

---

# 19. Çok önemli metodolojik sınırlamalar

## 19.1 `user_pseudo_id` kişi değildir

GA4 `user_pseudo_id` genellikle browser/device instance seviyesindedir.

Aynı gerçek kişi:

- farklı cihazlarda,
- farklı browser'larda,
- cookie reset sonrası

birden fazla `user_pseudo_id` oluşturabilir.

Bu nedenle sonuçlar “gerçek müşteri” değil, kullanılan identity seviyesine göre yorumlanmalıdır.

---

## 19.2 Tracking hataları analizi etkiler

Duplicate `purchase` event'leri, eksik purchase event'leri veya yanlış revenue değerleri:

- purchase count
- revenue
- purchase gap
- churn classification

sonuçlarını etkileyebilir.

---

## 19.3 Dataset başlangıcı gerçek müşteri başlangıcı olmayabilir

Bir kullanıcı dataset'in ilk gününde görünüyorsa bu onun gerçek ilk ziyareti veya ilk purchase'ı olmak zorunda değildir.

Export daha sonra başlamış olabilir.

---

## 19.4 Dataset'in son tarihi kritik önemdedir

Analiz tarihi `MAX(event_date)` olduğu için dataset güncel değilse churn classification eski bir tarihe göre yapılır.

---

## 19.5 Right censoring / observation-window etkisi

Son purchase'ı analiz tarihine yakın olan kullanıcılar henüz churn olabilecek kadar gözlenmemiş olabilir.

Örneğin threshold 90 gün ama kullanıcı son purchase'ı 20 gün önce yaptıysa “active” olarak görünür; bu kullanıcının gelecekte churn olup olmayacağını bu analiz söylemez.

---

## 19.6 Churn classification prediction değildir

Bu tool:

```text
kim churn olacak?
```

sorusunu tahmin etmez.

Şu soruyu cevaplar:

```text
Seçilen inactivity threshold'a göre şu anda hangi historical purchaser'lar churned olarak sınıflanıyor?
```

---

## 19.7 Causal inference yapılmaz

Örneğin 6+ purchase kullanıcılarında churn daha düşükse:

```text
6 purchase yapmak churn'ü düşürür
```

sonucu çıkarılamaz.

Bu descriptive relationship'tir.

---

## 19.8 Seasonality dikkate alınmaz

Basic sürümde:

- aylık seasonality
- yıllık purchase cycle
- kampanya etkisi
- ürün yenileme süresi

model içinde ayrıca kontrol edilmez.

Uzun purchase cycle olan sektörlerde threshold buna göre değerlendirilmelidir.

---

# 20. Analiz sonucu nasıl sunulmalı?

Tek bir churn rate paylaşmak yerine şu çerçeve daha sağlıklıdır:

```text
Selected threshold: 90 days
Churn rate: 27%
Observed purchase-gap P90: 84 days
Gap coverage at 90 days: 91%
75-day sensitivity: 31%
105-day sensitivity: 24%
One-time purchaser churn: 43%
6+ purchase churn: 10%
```

Böylece kullanıcı hem sonucu hem de sonucun threshold seçimine bağlı olduğunu görür.

---

# 21. Önerilen analyst checklist

Analizi paylaşmadan önce kontrol edin:

- [ ] Doğru GCP project seçildi mi?
- [ ] Doğru GA4 dataset seçildi mi?
- [ ] `table_id` doğru mu?
- [ ] Dataset'in son event tarihi güncel mi?
- [ ] Purchase tracking güvenilir mi?
- [ ] Revenue implementasyonu doğru mu?
- [ ] Purchase-gap dağılımında yeterli observation var mı?
- [ ] Median / P75 / P90 / P95 kontrol edildi mi?
- [ ] Threshold sensitivity incelendi mi?
- [ ] One-time ve repeat purchaser farkı değerlendirildi mi?
- [ ] Churned revenue share “future lost revenue” olarak yanlış sunulmadı mı?
- [ ] `user_pseudo_id` identity sınırlaması belirtildi mi?

---

# 22. Kavram sözlüğü

**Grain**  
Bir tablodaki bir satırın neyi temsil ettiğidir. `churn_base` için grain = 1 `user_pseudo_id`.

**Purchaser**  
En az bir `purchase` event'i olan kullanıcı.

**Repeat purchaser**  
Birden fazla purchase yapan kullanıcı.

**Purchase gap**  
Bir kullanıcının iki ardışık distinct purchase günü arasındaki gün sayısı.

**Threshold**  
Churn sınıflandırması için kullanılan maksimum kabul edilen inactivity süresi.

**Churned purchaser**  
Son purchase'ından bu yana geçen süre threshold'u aşan purchaser.

**Percentile**  
Dağılımdaki gözlemlerin belirli oranının altında/eşit kaldığı değer.

**P90**  
Gözlemlerin yaklaşık %90'ının altında/eşit olduğu değer.

**IQR**  
P75 − P25. Dağılımın orta %50'sinin yayılımı.

**Sensitivity analysis**  
Threshold değiştiğinde churn sonucunun ne kadar değiştiğini kontrol etme yöntemi.

---

## Sonuç

Bu toolkit'in temel yaklaşımı şudur:

```text
Önce purchase davranışını anla
        ↓
Purchase-gap dağılımını incele
        ↓
Business olarak anlamlı threshold seç
        ↓
Churn classification çalıştır
        ↓
Threshold sensitivity ile sonucu test et
        ↓
Frequency ve revenue diagnostics ile churn kitlesini yorumla
```

Churn rate tek başına nihai cevap değildir. Asıl değer, churn rate'in **hangi davranışsal dağılım ve hangi threshold varsayımı altında oluştuğunu** birlikte görebilmektir.
