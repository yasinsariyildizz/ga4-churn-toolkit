# GA4 Churn Toolkit — Analiz ve Yorumlama Rehberi

Bu rehber, `ga4-churn-toolkit` içindeki purchase-based churn akışının metodolojisini ve çıktıların nasıl okunması gerektiğini açıklar. Hedef kitle; GA4 BigQuery export verisiyle çalışan digital analytics, marketing analytics, CRM analytics ve BI ekipleridir.

Bu çalışma bir **predictive churn modeli** değildir. Kullanıcıları gelecekte churn etme olasılıklarına göre skorlamaz. Mevcut GA4 purchase history üzerinden purchaser lifecycle'ı çıkarır ve seçilen inactivity window'a göre kullanıcıları sınıflandırır.

---

## 1. Analitik çerçeve

Temel yaklaşım purchaser-level recency mantığıdır.

Bir `user_pseudo_id` en az bir `purchase` event'i üretmişse purchaser base'e dahil edilir. Her purchaser için son purchase tarihi ile dataset'teki son gözlem tarihi arasındaki fark hesaplanır:

```text
days_since_last_purchase = analysis_date - last_purchase_date
```

Churn cutoff analiz çalıştırılırken verilir:

```python
analysis.churn_analysis(90)
```

90 günlük örnekte segmentasyon mantığı:

```text
purchase_count = 0
→ never_purchased

purchase_count > 0
ve days_since_last_purchase <= 90
→ active_purchaser

purchase_count > 0
ve days_since_last_purchase > 90
→ churned
```

Buradaki churn tanımı bir **behavioral inactivity rule**'dur. Abonelik iptali, CRM status'ü veya resmi müşteri kaybı kaydı değildir.

---

## 2. Metric scope ve analiz tarihi

Analiz tarihi ayrıca input olarak girilmez:

```text
analysis_date = MAX(event_date)
```

Bu tercih workflow'u basitleştirir; ancak data freshness kritik hale gelir.

Örnek:

```text
Bugün: 20 Eylül
Dataset'in son event_date'i: 31 Ağustos
```

Bu durumda churn classification 20 Eylül'e göre değil, 31 Ağustos'a göre yapılır.

Bu nedenle churn sonucunu paylaşmadan önce her zaman `analysis_date` kontrol edilmelidir.

---

## 3. Input modeli

```python
analysis = ChurnAnalysis(
    project_id="your-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

| Input | Kullanım |
|---|---|
| `project_id` | GA4 export'un bulunduğu GCP project |
| `dataset_id` | GA4 BigQuery export dataset |
| `table_id` | Kaynak tablo veya wildcard (`events_*`) |
| `output_dataset_id` | Analiz tablolarının yazılacağı dataset |

Churn threshold constructor'a verilmez. Bunun nedeni cutoff kararının purchase cadence incelendikten sonra verilmesidir.

---

# 4. Önerilen workflow

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

Bu akış şu sorulara cevap verir:

```text
1. Ne kadar data taranacak?
2. Purchaser base nasıl görünüyor?
3. Repeat purchase davranışına göre makul inactivity window ne olabilir?
4. Seçilen cutoff'ta churn görünümü nasıl değişiyor?
```

---

# 5. `dry_run()` — Query cost kontrolü

```python
analysis.dry_run()
```

BigQuery sorguları çalıştırılmadan önce estimated bytes scanned gösterilir.

Ana çıktı:

```text
Estimated scan: X GB
```

Bu metrik business KPI değildir. Query footprint kontrolüdür.

Özellikle `table_id="events_*"` kullanılıyorsa export history'nin tamamı taranabilir.

Kontrol edilmesi gerekenler:

- yanlış property / dataset seçimi,
- gereksiz full-history scan,
- beklenenden yüksek query volume,
- test sırasında production-size dataset kullanımı.

Ajans veya multi-client yapılarda bu adım cost governance açısından önemlidir.

---

# 6. `create_base_table()` — Purchaser-level analytical base

```python
analysis.create_base_table()
```

Output grain:

```text
1 row = 1 user_pseudo_id
```

Çıktı tablo:

```text
<output_dataset>.churn_base
```

Bu tablo churn analysis'in user-level feature layer'ıdır.

## Ana kolonlar

| Kolon | Tanım |
|---|---|
| `user_pseudo_id` | GA4 device/browser scoped user identifier |
| `first_event_date` | Export içinde görülen ilk event tarihi |
| `last_event_date` | Export içinde görülen son event tarihi |
| `event_count` | Toplam event volume |
| `session_count` | Distinct `ga_session_id` sayısı |
| `purchase_count` | Purchase event sayısı |
| `revenue` | `ecommerce.purchase_revenue` toplamı |
| `first_purchase_date` | İlk gözlenen purchase tarihi |
| `last_purchase_date` | Son gözlenen purchase tarihi |
| `analysis_date` | Kaynak dataset'teki maksimum `event_date` |
| `days_since_last_purchase` | Purchase recency |

## Users

Distinct `user_pseudo_id` sayısıdır. Gerçek kişi sayısı olarak yorumlanmamalıdır; GA4 identity scope nedeniyle aynı kişi farklı device/browser/cookie state altında birden fazla `user_pseudo_id` üretebilir.

## Purchasers

En az bir purchase event'i olan user base. Churn denominator'ının temelini oluşturur.

## One-time purchasers

Sadece bir purchase kaydı olan kullanıcılar. Acquisition sonrası repeat davranışı oluşmamış purchaser'ları temsil eder.

## Repeat purchasers

Birden fazla purchase kaydı olan kullanıcılar. Repeat-purchase cadence analizinin ana gözlem kitlesidir.

## Purchaser rate

```text
purchasers / observed users
```

Bu bir conversion rate değildir; session-level funnel conversion ile karıştırılmamalıdır. User-level observed purchaser share'dir.

## Repeat rate

```text
repeat purchasers / purchasers
```

Purchaser base'in ne kadarının birden fazla satın alma davranışı gösterdiğini özetler.

## Revenue

GA4 purchase event'lerinde bulunan historical revenue toplamıdır. Duplicate purchase, transaction deduplication eksikliği, currency mapping, missing revenue ve consent / implementation gaps metriği etkileyebilir. GA4 revenue ile finance / ERP revenue'nun birebir aynı olması beklenmemelidir.

---

# 7. `purchase_day_distribution()` — Repeat-purchase cadence

```python
analysis.purchase_day_distribution()
```

Bu fonksiyon threshold seçmeden önce repurchase timing'in shape'ini anlamak için kullanılır.

Distinct purchase günleri user bazında sıralanır ve ardışık purchase günleri arasındaki fark hesaplanır.

Örnek:

```text
10 Ocak
25 Ocak
20 Şubat
```

üretilen gap'ler:

```text
15 gün
26 gün
```

Aynı gün içindeki birden fazla purchase tek purchase date olarak değerlendirilir. Böylece order frequency ile day-gap distribution birbirine karıştırılmaz.

One-time purchasers bu analize dahil değildir; çünkü hesaplanabilecek repeat interval yoktur.

---

# 8. Distribution metrics

## Gap observations

Toplam ardışık purchase interval sayısıdır. Bir kullanıcı 5 distinct purchase date'e sahipse 4 gap observation üretir. Bu nedenle `gap observations != repeat purchasers` olması beklenen bir durumdur.

## Mean gap

Purchase interval ortalamasıdır. Long-tail behavior'dan etkilenir; tek başına inactivity cutoff olarak kullanılmamalıdır.

## Median / P50

Repeat-purchase cadence'in merkezi için daha robust bir referanstır.

```text
Median = 32 gün
```

ise observed gap'lerin yaklaşık yarısı 32 gün veya daha kısadır.

## P25 / P75

Purchase cadence'in middle 50% range'ini gösterir.

```text
P25 = 18
P75 = 56
```

ise core repeat behavior yaklaşık 18–56 gün bandında yoğunlaşıyor olabilir.

## IQR

```text
IQR = P75 - P25
```

Behavioral dispersion göstergesidir. Dar IQR daha standardize repeat cadence'e, geniş IQR ise daha heterojen purchaser behavior'a işaret edebilir.

## P90 / P95

Threshold calibration için upper-tail referanslardır.

```text
P90 = 84 gün
P95 = 126 gün
```

Bu durumda 90 günlük cutoff, historical repeat intervals'ın üst bandına yakın bir noktadadır.

P90 veya P95 doğrudan churn threshold değildir; behavioral baseline sağlar. Category cycle, replenishment period, seasonality ve CRM strategy ayrıca değerlendirilmelidir.

## Standard deviation

Purchase-gap volatility'yi gösterir. Yüksek değer, purchaser'ların repurchase cadence açısından homojen olmadığını gösterebilir.

## Coefficient of Variation

```text
CV = standard deviation / mean
```

Scale-independent dispersion measure olarak kullanılır.

Pratik diagnostic:

```text
CV < 0.5   → relatively concentrated cadence
0.5–1.0    → moderate variability
CV >= 1.0  → high variability
```

Bu seviyeler hard rule değildir.

---

# 9. Purchase-gap histogram

Bucket'lar:

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

Her bar ilgili interval bandındaki observation volume'u gösterir.

Yoğunluk 15–30 ve 31–60 bucket'larında ise purchaser base'in önemli kısmı iki aylık window içinde repeat purchase yapıyor olabilir.

181+ bucket'ları güçlüyse şu faktörler incelenmelidir:

- long replenishment cycle,
- seasonal purchase pattern,
- farklı product/category mix,
- high-value / low-frequency segmentler,
- çok uzun observation window.

Histogram threshold kararını tek başına vermez; distribution shape'i görünür hale getirir.

---

# 10. Cumulative repeat-purchase coverage

Bu grafik şu soruyu cevaplar:

```text
Observed purchase intervals'ın yüzde kaçı X gün içinde gerçekleşti?
```

Örnek:

```text
30 gün  → %46
60 gün  → %73
90 gün  → %89
180 gün → %97
```

90 günlük cutoff için %89 coverage varsa historical repeat intervals'ın yaklaşık %89'u 90 gün veya daha kısadır.

Bu, kullanıcıların %89'unun 90 günde geri geldiği anlamına gelmez. Metric scope interval-level'dır, user-level değildir.

---

# 11. Purchase behavior readout

Notebook, distribution sonuçlarından kısa analyst notes üretir.

Örnek:

```text
Median repeat-purchase interval: 31 days
Middle 50% range: 18–55 days
Distribution: right-skewed
Cadence variability: high
```

Bu notların amacı output'u hızlı scan edilebilir hale getirmektir. Threshold kararı analyst / business owner tarafından verilmelidir.

---

# 12. `churn_analysis(threshold)` — Purchaser inactivity classification

```python
analysis.churn_analysis(90)
```

Churn rate:

```text
churned purchasers / all purchasers
```

Never-purchased users denominator dışında tutulur.

Örnek:

```text
Observed users      1,000,000
Purchasers            200,000
Churned                60,000

Churn rate = 60,000 / 200,000 = 30%
```

60,000 / 1,000,000 kullanmak purchaser churn metric'ini dilute eder.

---

# 13. Churn KPI'ları

## Active purchasers

Son purchase'ı seçilen inactivity window içinde kalan purchaser'lar.

## Churned purchasers

Son purchase'tan bu yana geçen süre cutoff'u aşan purchaser'lar.

## One-time purchasers

Acquisition sonrası repeat satın alma davranışı göstermemiş purchaser base.

## Churned one-time buyers

Bir purchase sonrası cutoff'u aşmış kullanıcılar.

## Churned repeat buyers

Repeat history olmasına rağmen recency threshold'u aşmış kullanıcılar.

Bu ayrım CRM activation açısından önemlidir. One-time lapse ile established repeat purchaser lapse aynı lifecycle problem olmayabilir.

---

# 14. Churned historical revenue share

```text
historical revenue from churned purchasers
-----------------------------------------
historical revenue from all purchasers
```

Bu metric revenue exposure view sağlar.

Örnek:

```text
Churn rate = %25
Churned historical revenue share = %41
```

ise churned segment geçmişte purchaser revenue'nun orantısız derecede büyük bir kısmını üretmiş olabilir.

Bu metric `lost revenue`, `future revenue loss` veya `incremental revenue opportunity` olarak adlandırılmamalıdır. Historical contribution ile future loss aynı şey değildir.

---

# 15. Status diagnostics

Active, churned ve never-purchased gruplar karşılaştırılır.

Öne çıkan kolonlar:

- user volume,
- average purchases,
- median purchases,
- average revenue,
- median revenue,
- average inactivity days.

Mean + median birlikte okunmalıdır.

```text
Active avg revenue    = 1,250
Active median revenue = 310
```

farkı high-value tail'in mean'i yukarı çektiğini gösterebilir. Digital commerce datalarında revenue distribution çoğu zaman right-skewed olduğu için median business readout'ta özellikle değerlidir.

---

# 16. Purchaser status chart

Active ve churned purchaser base'in absolute volume karşılaştırmasıdır. Grafik rate değil volume gösterir. Bar size, churn rate ve purchaser base size birlikte değerlendirilmelidir.

---

# 17. Churn rate by purchase frequency

Segmentler:

```text
1 purchase
2 purchases
3–5 purchases
6+ purchases
```

Her segment için churn rate ayrı hesaplanır. Bu kırılım purchaser depth ile retention behavior arasındaki ilişkiyi görmeye yarar.

Örnek:

```text
1 purchase   → %52
2 purchases  → %34
3–5          → %19
6+           → %10
```

Bu tablo lifecycle segmentation için güçlü bir diagnostic olabilir. Ancak sonuç descriptive'dir. Purchase frequency ile churn arasında association görmek causal effect kanıtlamaz.

---

# 18. Threshold sensitivity

Bu grafik churn metric'inin cutoff assumption'a ne kadar bağlı olduğunu gösterir.

90 günlük threshold için örnek:

```text
60 gün  → %36
75 gün  → %31
90 gün  → %27
105 gün → %24
120 gün → %21
150 gün → %17
```

Threshold büyüdükçe churn classification daha konservatif hale gelir ve churn rate genellikle düşer.

### Stable case

```text
75 gün  = %30
90 gün  = %29
105 gün = %28
```

Cutoff choice metric'i sınırlı etkiliyor.

### Sensitive case

```text
75 gün  = %42
90 gün  = %29
105 gün = %18
```

Metric cutoff assumption'a çok hassastır. Bu durumda churn rate'i tek bir kesin KPI gibi sunmak yerine sensitivity band ile raporlamak daha sağlıklıdır.

---

# 19. Threshold context / gap coverage

Selected cutoff historical repeat-purchase distribution üzerinde konumlandırılır.

```text
Threshold = 90 gün
Gap coverage = %91
P90 = 86 gün
```

Bu yapı şu business readout'u destekler:

```text
90 günlük inactivity window, observed repeat-purchase intervals'ın yaklaşık %91'ini kapsıyor ve historical P90'ın biraz üzerinde konumlanıyor.
```

Bu behavioral sanity check'tir; optimum değer kanıtı değildir.

---

# 20. Threshold calibration yaklaşımı

Threshold calibration sırasında birlikte değerlendirilmesi gerekenler:

1. median purchase gap,
2. P75 / P90 / P95,
3. histogram shape,
4. cumulative coverage,
5. sensitivity curve,
6. category replenishment cycle,
7. seasonality,
8. campaign / promotion cadence,
9. CRM contact strategy,
10. observation-window length.

Örnek:

```text
Median = 29
P75 = 51
P90 = 87
P95 = 128
```

Test senaryoları 60 / 90 / 120 gün olabilir. Doğru cutoff yalnızca distribution'a değil business use case'e de bağlıdır.

---

# 21. HTML dashboard

`churn_analysis()` sonunda `ga4_churn_dashboard.html` oluşturulur.

Dashboard şu readout'ları taşır:

- selected inactivity threshold,
- purchaser base,
- active purchaser volume,
- churned purchaser volume,
- churn rate,
- gap coverage,
- churned historical revenue share,
- status diagnostics,
- churn by purchase frequency,
- threshold sensitivity,
- analyst notes.

Dashboard operational sharing için uygundur; metric definitions notebook ile aynıdır.

---

# 22. Measurement caveats

## `user_pseudo_id` customer ID değildir

GA4 `user_pseudo_id` çoğunlukla device/browser scope'tadır. Aynı kişi mobile + desktop, farklı browser, cookie reset veya consent state değişimi nedeniyle birden fazla identifier üretebilir.

Logged-in user stitching yapılmıyorsa sonuçlar customer-level değil, GA4 observed-user level'dır.

## Purchase tracking quality

Aşağıdaki implementation sorunları churn output'unu doğrudan bozar:

- duplicate purchase,
- missing purchase,
- broken transaction_id,
- revenue duplication,
- currency mismatch,
- late / partial tagging.

Churn analysis öncesi ecommerce tracking QA yapılması önerilir.

## Export start date bias

BigQuery export'un başlangıç tarihi müşteri lifecycle başlangıcı değildir. Export yeni başladıysa `first_purchase_date`, `purchase_count` ve `repeat rate` historical lifecycle'ı eksik gösterebilir.

## Observation-window bias

Threshold 90 günse ancak son 30 günlük purchaser'lar için henüz 90 günlük outcome window tamamlanmamıştır. Bu kullanıcılar active görünür; bu gelecekte churn etmeyecekleri anlamına gelmez.

## Classification ≠ prediction

Bu framework şu soruya cevap verir:

```text
Selected inactivity rule'a göre hangi purchasers şu anda churned segmentinde?
```

Şu soruya cevap vermez:

```text
Önümüzdeki 30 günde kim churn edecek?
```

Prediction için ayrı feature engineering, training window, outcome definition ve model validation gerekir.

## Seasonality

Basic sürüm seasonality adjustment yapmaz. Travel, insurance, annual renewal, gifting, fashion seasonality ve durable goods gibi kategorilerde global threshold dikkatli kullanılmalıdır.

---

# 23. Reporting önerisi

Tek bir churn rate yerine context ile birlikte raporlamak daha sağlıklıdır.

```text
Inactivity threshold          90 days
Purchaser churn rate          27%
Observed gap P90              84 days
Gap coverage @ 90d            91%
Churn @ 75d                   31%
Churn @ 105d                  24%
One-time purchaser churn      43%
6+ purchase churn             10%
Churned historical rev. share 38%
```

Bu format hem metric'i hem underlying assumption'ı görünür tutar.

---

# 24. Analyst checklist

- [ ] Source GCP project doğru mu?
- [ ] GA4 dataset / property doğru mu?
- [ ] `events_*` scope beklenen tarih aralığını kapsıyor mu?
- [ ] Dataset fresh mi?
- [ ] Purchase event QA tamam mı?
- [ ] Revenue / currency mapping doğru mu?
- [ ] Duplicate transaction riski kontrol edildi mi?
- [ ] Purchaser base anlamlı büyüklükte mi?
- [ ] Repeat purchaser observation yeterli mi?
- [ ] P50 / P75 / P90 / P95 incelendi mi?
- [ ] Histogram ve cumulative coverage okundu mu?
- [ ] Threshold sensitivity kontrol edildi mi?
- [ ] One-time vs repeat purchaser farkı değerlendirildi mi?
- [ ] Historical revenue share future lost revenue olarak etiketlenmedi mi?
- [ ] `user_pseudo_id` identity limitation dokümante edildi mi?

---

# 25. Terminology

**Grain** — Bir satırın temsil ettiği analytical unit. `churn_base` için grain = 1 `user_pseudo_id`.

**Purchaser base** — En az bir purchase event'i olan observed user seti.

**Repeat purchaser** — Birden fazla purchase history'si olan purchaser.

**Purchase cadence** — Purchaser'ların tekrar satın alma zamanlaması.

**Purchase gap** — Ardışık distinct purchase dates arasındaki gün farkı.

**Recency** — Son purchase'tan analysis date'e geçen süre.

**Inactivity threshold / cutoff** — Purchaser'ın churned olarak sınıflandırılması için kullanılan recency sınırı.

**P90** — Observed interval'ların yaklaşık %90'ının altında/eşit olduğu değer.

**IQR** — P75 − P25; distribution'ın middle 50% spread'i.

**Sensitivity analysis** — Cutoff değiştiğinde churn metric'inin ne kadar değiştiğini test etme yaklaşımı.

**Metric scope** — Bir KPI'ın hangi population ve grain üzerinde hesaplandığını tanımlar.

---

## Özet

```text
Validate query scope
        ↓
Build purchaser-level base
        ↓
Profile repeat-purchase cadence
        ↓
Select a business-relevant inactivity window
        ↓
Classify active vs churned purchasers
        ↓
Check threshold sensitivity
        ↓
Read frequency + revenue diagnostics
        ↓
Use outputs for lifecycle / CRM / retention analysis
```

Ana prensip: churn rate tek başına yeterli değildir. Metric'in hangi purchaser base, hangi observation window ve hangi inactivity cutoff altında oluştuğu her zaman görünür olmalıdır.
