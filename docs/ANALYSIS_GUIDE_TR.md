# GA4 Churn Toolkit — Türkçe Kullanım ve Yorumlama Rehberi

Bu rehber, churn analizini ilk defa gören birinin bile mantığı anlayabilmesi için hazırlanmıştır. Burada amaç sadece kodu çalıştırmak değil; çıkan sayıların ve grafiklerin ne anlattığını doğru yorumlamaktır.

Bu araç GA4 verisindeki satın alma hareketlerine bakar. Bir kullanıcının en son ne zaman alışveriş yaptığını bulur ve seçtiğimiz gün sayısına göre kullanıcının hâlâ aktif mi yoksa artık geri dönmemiş mi olduğunu sınıflandırır.

Örneğin:

```python
analysis.churn_analysis(90)
```

Buradaki `90`, son alışverişten sonra 90 gün geçmişse kullanıcıyı churn olmuş kabul et demektir.

Bu araç geleceği tahmin etmez. Yani “bu kullanıcı yakında churn olacak” demez. Sadece elimizdeki geçmiş veriye bakıp kullanıcıları mevcut durumlarına göre ayırır.

---

## 1. Analizin temel mantığı

Önce her kullanıcının son satın alma tarihi bulunur.

Sonra veri içindeki en güncel tarih ile kullanıcının son satın alma tarihi arasındaki gün farkı hesaplanır.

Basit olarak:

```text
Son alışverişten bu yana geçen gün
=
verideki en güncel tarih - son alışveriş tarihi
```

Örnek:

```text
Verideki en güncel tarih: 30 Eylül
Kullanıcının son alışverişi: 10 Haziran
Aradan geçen süre: 112 gün
```

Eğer analizde 90 gün seçildiyse bu kullanıcı churn olmuş sayılır.

Sınıflandırma şu şekilde yapılır:

```text
Hiç alışveriş yapmamış
→ never_purchased

En az bir alışveriş yapmış
ve son alışverişinin üzerinden seçilen süreden daha az zaman geçmiş
→ active_purchaser

En az bir alışveriş yapmış
ve son alışverişinin üzerinden seçilen süreden daha fazla zaman geçmiş
→ churned
```

Buradaki önemli nokta şu:

**Hiç alışveriş yapmamış kullanıcı churn olmuş sayılmaz.** Çünkü bu kişinin kaybedilmiş müşteri olması için önce müşteri olması gerekir.

---

## 2. Analiz hangi tarihi baz alıyor?

Kullanıcı ayrıca bir analiz tarihi girmiyor.

Araç, kaynak veride gördüğü en güncel günü kullanıyor:

```text
analysis_date = verideki en büyük event_date
```

Örneğin bugün 20 Eylül olabilir ama BigQuery tablosundaki son veri 31 Ağustos'a ait olabilir.

Bu durumda churn hesabı 20 Eylül'e göre değil, 31 Ağustos'a göre yapılır.

Bu yüzden sonuçlara bakarken ilk kontrol edilmesi gerekenlerden biri şudur:

> Verinin son tarihi gerçekten güncel mi?

Eğer veri 20 gün geriden geliyorsa churn sonucu da 20 gün geriden gelecektir.

---

## 3. Başlangıçta hangi bilgileri giriyoruz?

```python
analysis = ChurnAnalysis(
    project_id="your-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

Burada dört bilgi var:

| Alan | Ne işe yarıyor? |
|---|---|
| `project_id` | GA4 verisinin bulunduğu Google Cloud projesi |
| `dataset_id` | GA4 verisinin bulunduğu BigQuery dataset'i |
| `table_id` | Okunacak tablo. Genelde `events_*` |
| `output_dataset_id` | Analiz sonucunda oluşturulacak tabloların yazılacağı dataset |

Churn için kullanılacak gün sayısı burada girilmez.

Bunun nedeni şu: önce satın alma aralıklarını görmek, sonra uygun gün sayısına karar vermek daha sağlıklıdır.

---

# 4. Analizi hangi sırayla çalıştırıyoruz?

Önerilen sıra:

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

Bu sırayı ofiste şöyle düşünebilirsin:

```text
1. Bu sorgu ne kadar veri okuyacak?
2. Kullanıcıların genel satın alma görünümü nasıl?
3. Kullanıcılar normalde kaç günde bir tekrar alışveriş yapıyor?
4. Buna göre 90 gün gibi bir sınır seçince kaç kişi churn oluyor?
```

---

# 5. `dry_run()` ne yapıyor?

```python
analysis.dry_run()
```

Bu adım henüz analizi çalıştırmaz.

Sadece BigQuery'nin yaklaşık ne kadar veri okuyacağını gösterir.

Örnek:

```text
Estimated scan: 48 GB
```

Bu sayı bir analiz sonucu değildir.

Yani “48 GB kullanıcı var” gibi bir anlamı yoktur.

Sadece sorgu çalışırsa yaklaşık 48 GB veri taranacağını gösterir.

Bu özellikle maliyet kontrolü için önemlidir.

### Ne zaman dikkat etmek gerekir?

Örneğin normalde birkaç aylık veri beklerken 2 TB tarama görünüyorsa şunlar kontrol edilmelidir:

- Yanlış proje mi seçildi?
- Yanlış dataset mi seçildi?
- `events_*` ile gereğinden fazla tarih mi taranıyor?
- Test için bütün geçmiş veriyi okumaya gerçekten gerek var mı?

Bu adımı “ön kontrol” gibi düşünebilirsin.

---

# 6. `create_base_table()` ne yapıyor?

```python
analysis.create_base_table()
```

Bu fonksiyon her kullanıcı için tek satırlık bir özet tablo oluşturur.

Yani:

```text
1 satır = 1 user_pseudo_id
```

Buradaki `user_pseudo_id`, GA4'ün cihaz ve tarayıcı bazlı kullanıcı kimliğidir.

Bunu “kesin gerçek kişi” gibi düşünmemek gerekir.

Aynı kişi:

- telefondan girdiğinde,
- bilgisayardan girdiğinde,
- farklı tarayıcı kullandığında,
- çerezleri sildiğinde

farklı `user_pseudo_id` değerleri oluşturabilir.

Bu yüzden sonuçları “gerçek müşteri sayısı” değil, GA4'ün görebildiği kullanıcı kimliği seviyesinde yorumlamak gerekir.

---

## 7. Temel tabloda hangi bilgiler var?

Her kullanıcı için aşağıdaki bilgiler hazırlanır:

| Alan | Açıklama |
|---|---|
| `user_pseudo_id` | GA4 kullanıcı kimliği |
| `first_event_date` | Bu kullanıcının veride görüldüğü ilk gün |
| `last_event_date` | Veride görüldüğü son gün |
| `event_count` | Toplam yaptığı hareket sayısı |
| `session_count` | Toplam oturum sayısı |
| `purchase_count` | Kaç alışveriş yaptığı |
| `revenue` | GA4'e göre toplam alışveriş geliri |
| `first_purchase_date` | İlk alışveriş tarihi |
| `last_purchase_date` | Son alışveriş tarihi |
| `analysis_date` | Kaynak verideki en güncel tarih |
| `days_since_last_purchase` | Son alışverişten bu yana geçen gün |

Bu tablo daha sonraki bütün churn hesaplarının temelini oluşturur.

---

# 8. Base table ekranındaki sayılar nasıl okunmalı?

## Users

Veride görülen toplam farklı `user_pseudo_id` sayısıdır.

Gerçek kişi sayısıyla birebir aynı olmak zorunda değildir.

## Purchasers

En az bir kere alışveriş yapmış kullanıcı sayısıdır.

Churn hesabında asıl baktığımız kitle budur.

## One-time purchasers

Sadece bir kez alışveriş yapan kullanıcılardır.

Bu grup önemlidir çünkü tek alışveriş yapan kullanıcılarla sürekli alışveriş yapan kullanıcıların davranışı genelde aynı değildir.

## Repeat purchasers

Birden fazla alışveriş yapan kullanıcılardır.

Bu kullanıcılar bize “normalde kaç günde bir tekrar alışveriş yapılıyor?” sorusunu cevaplamada yardımcı olur.

## Purchaser rate

```text
alışveriş yapan kullanıcı / tüm kullanıcılar
```

Örnek:

```text
100.000 kullanıcı
10.000 alışveriş yapan kullanıcı

Purchaser rate = %10
```

Bu churn oranı değildir.

Ayrıca klasik e-ticaret dönüşüm oranı gibi de düşünülmemelidir. Çünkü burada oturum değil kullanıcı bazında bakıyoruz.

## Repeat rate

```text
birden fazla alışveriş yapan kullanıcı / alışveriş yapan tüm kullanıcılar
```

Örnek:

```text
10.000 alışveriş yapan kullanıcı
3.000 tekrar alışveriş yapan kullanıcı

Repeat rate = %30
```

Bu bize alışveriş yapan kitlenin ne kadarının yeniden geldiğini gösterir.

## Revenue

GA4'te kayıtlı toplam alışveriş geliridir.

Burada önemli bir uyarı var:

GA4 geliri ile şirketin muhasebe veya ERP sistemindeki gelir birebir aynı olmayabilir.

Sebep olarak:

- eksik takip,
- aynı siparişin iki kez gönderilmesi,
- yanlış para birimi,
- iptal/iade farkları,
- takip hataları

etkili olabilir.

Bu nedenle gelir rakamı kullanılmadan önce GA4 kurulumunun doğru olduğundan emin olunmalıdır.

---

# 9. `purchase_day_distribution()` ne yapıyor?

```python
analysis.purchase_day_distribution()
```

Bu bölüm aslında churn analizinin en önemli hazırlık adımıdır.

Amaç şudur:

> Kullanıcılar normalde iki alışveriş arasında kaç gün bekliyor?

Örneğin bir kullanıcı şu tarihlerde alışveriş yapmış olsun:

```text
10 Ocak
25 Ocak
20 Şubat
```

Bu kullanıcı için iki bekleme süresi oluşur:

```text
10 Ocak → 25 Ocak = 15 gün
25 Ocak → 20 Şubat = 26 gün
```

Sistem bütün tekrar alışveriş yapan kullanıcılar için bu aralıkları hesaplar.

Aynı gün içinde iki alışveriş varsa o gün tek gün olarak alınır.

Yani:

```text
10 Ocak sabah alışveriş
10 Ocak akşam alışveriş
```

iki ayrı gün aralığı oluşturmaz.

---

# 10. Gap Observations ne demek?

Bu sayı toplam kaç alışveriş aralığı hesaplandığını gösterir.

Örneğin bir kullanıcı 5 farklı günde alışveriş yaptıysa:

```text
1. alışveriş → 2. alışveriş
2. alışveriş → 3. alışveriş
3. alışveriş → 4. alışveriş
4. alışveriş → 5. alışveriş
```

toplam 4 aralık oluşur.

Bu yüzden:

```text
alışveriş aralığı sayısı
```

ile

```text
tekrar alışveriş yapan kullanıcı sayısı
```

aynı olmak zorunda değildir.

---

# 11. Mean yani ortalama alışveriş aralığı

Bu, bütün alışveriş aralıklarının ortalamasıdır.

Örnek:

```text
10 gün
12 gün
14 gün
15 gün
180 gün
```

180 günlük çok uzun bir değer ortalamayı ciddi şekilde yukarı çekebilir.

Bu yüzden sadece ortalamaya bakıp churn sınırı seçmek doğru değildir.

---

# 12. Median yani ortanca değer

Median, değerleri küçükten büyüğe sıraladığımızda ortada kalan değerdir.

Örneğin:

```text
10
12
14
15
180
```

burada median 14'tür.

Ortalama ise 46'dan fazladır.

Görüldüğü gibi uzun süre bekleyen birkaç kullanıcı ortalamayı yükseltirken median daha dengeli bir fikir verebilir.

Bu nedenle satın alma aralıklarını değerlendirirken median çoğu zaman daha faydalıdır.

Örnek:

```text
Median = 31 gün
```

Bu, gözlenen alışveriş aralıklarının yaklaşık yarısının 31 gün veya daha kısa olduğunu gösterir.

---

# 13. P25, P75, P90 ve P95 ne demek?

Bunları mümkün olduğunca basit düşünelim.

## P25

Alışveriş aralıklarının yaklaşık %25'i bu gün sayısının altında veya eşittir.

## P75

Alışveriş aralıklarının yaklaşık %75'i bu gün sayısının altında veya eşittir.

Örnek:

```text
P25 = 18 gün
P75 = 55 gün
```

Bu durumda alışveriş aralıklarının orta bölümünün büyük kısmı yaklaşık 18–55 gün arasındadır.

## P90

Alışveriş aralıklarının yaklaşık %90'ı bu sürenin altında veya eşittir.

Örnek:

```text
P90 = 84 gün
```

Bu şu anlama gelir:

> Gözlemlediğimiz tekrar alışveriş aralıklarının yaklaşık %90'ı 84 gün içinde gerçekleşmiş.

Bu yüzden 90 gün gibi bir churn sınırı seçmek mantıklı bir aday olabilir.

Ama bu kesin kural değildir.

## P95

Aynı mantıkla alışveriş aralıklarının yaklaşık %95'inin altında kaldığı süreyi gösterir.

P95 genelde daha uzun bekleyen müşterileri de içine alan daha geniş bir bakış sunar.

---

# 14. IQR ne anlatıyor?

IQR şu şekilde hesaplanır:

```text
P75 - P25
```

Örnek:

```text
P25 = 20 gün
P75 = 50 gün
IQR = 30 gün
```

Bu değer, kullanıcıların orta bölümünde alışveriş aralıklarının ne kadar yayıldığını gösterir.

IQR düşükse kullanıcıların davranışı birbirine daha yakın olabilir.

IQR yüksekse bazı kullanıcılar çok hızlı, bazıları çok geç tekrar alışveriş yapıyor olabilir.

Bu durumda herkese aynı churn sınırını uygulamak daha tartışmalı hale gelir.

---

# 15. Standart sapma ne anlatıyor?

Standart sapma, alışveriş aralıklarının birbirinden ne kadar farklı olduğunu anlamaya yarar.

Yüksekse kullanıcı davranışları daha dağınıktır.

Düşükse kullanıcıların alışveriş aralıkları birbirine daha yakındır.

Bu değeri tek başına yorumlamak yerine median, P75 ve P90 ile birlikte okumak daha sağlıklıdır.

---

# 16. Coefficient of Variation ne anlatıyor?

Arayüzde bu değer görünüyorsa basitçe şöyle düşün:

> Alışveriş aralıkları kendi ortalamasına göre ne kadar dağınık?

Kabaca:

```text
0.5'in altı  → daha düzenli davranış
0.5–1 arası  → orta seviyede farklılık
1 ve üzeri   → oldukça değişken davranış
```

Bunlar kesin kurallar değildir.

Sadece “herkese tek bir churn süresi uygulamak ne kadar mantıklı?” sorusuna yardımcı olur.

---

# 17. Purchase-gap histogram grafiği nasıl okunur?

Grafikte alışverişler arasındaki bekleme süreleri gruplara ayrılır:

```text
0–7 gün
8–14 gün
15–30 gün
31–60 gün
61–90 gün
91–180 gün
181–365 gün
366+ gün
```

Her çubuğun uzunluğu o aralıkta kaç alışveriş bekleme süresi olduğunu gösterir.

Örneğin en yüksek çubuk:

```text
15–30 gün
```

ise birçok tekrar alışveriş 15–30 gün arasında gerçekleşiyor olabilir.

Eğer 181 gün ve üzerindeki çubuklar da yüksekse bunun birkaç nedeni olabilir:

- ürün çok sık alınan bir ürün değildir,
- müşteri grupları birbirinden farklı davranıyordur,
- bazı ürünler mevsimseldir,
- veri geçmişi çok uzundur,
- kullanıcıların bir kısmı gerçekten çok geç geri dönüyordur.

Buradan doğrudan:

```text
En yüksek çubuk 31–60 gün, o zaman churn süresi 60 gün olmalı
```

gibi bir sonuç çıkarılmamalıdır.

Grafik bize davranışın şeklini gösterir. Kararı tek başına vermez.

---

# 18. Cumulative Repeat-Purchase Coverage grafiği nasıl okunur?

Bu grafik şu soruya cevap verir:

> Alışverişler arasındaki bekleme sürelerinin yüzde kaçı belirli bir günün içinde kalıyor?

Örnek:

```text
30 gün  → %48
60 gün  → %72
90 gün  → %89
180 gün → %97
```

Bunun anlamı:

- alışveriş aralıklarının %48'i 30 gün içinde,
- %72'si 60 gün içinde,
- %89'u 90 gün içinde,
- %97'si 180 gün içinde gerçekleşmiş.

Bu grafik churn sınırı seçerken çok faydalıdır.

Örneğin 90 günlük sınır seçtiğinde %89 görünüyorsa, geçmişte gözlenen alışveriş aralıklarının yaklaşık %89'u zaten 90 gün içinde gerçekleşmiş demektir.

Ama bu:

```text
Kullanıcıların %89'u 90 günde geri geliyor
```

demek değildir.

Burada kullanıcı sayısını değil, iki alışveriş arasındaki süreleri sayıyoruz.

---

# 19. Purchase Behavior Insights bölümü nasıl okunmalı?

Araç, hesaplanan sonuçlardan kısa açıklamalar üretir.

Örneğin:

```text
Median repeat-purchase interval is 31 days.
90% of observed intervals are below 84 days.
Repurchase timing is highly variable.
```

Bu cümleler yeni bir hesap yapmaz.

Sadece ekrandaki sayıların daha hızlı okunmasını sağlar.

Asıl karar yine analizi yapan kişiye aittir.

---

# 20. `churn_analysis(90)` ne yapıyor?

```python
analysis.churn_analysis(90)
```

Bu örnekte sistem şunu sorar:

> Son alışverişinin üzerinden 90 günden fazla zaman geçen kaç müşterimiz var?

Sonra alışveriş yapmış kullanıcıları iki gruba ayırır:

```text
90 gün veya daha az geçmiş
→ active_purchaser

90 günden fazla geçmiş
→ churned
```

Hiç alışveriş yapmamışlar ayrı tutulur.

---

# 21. Churn rate nasıl hesaplanıyor?

Formül:

```text
churn olmuş alışveriş yapan kullanıcılar
---------------------------------------
tüm alışveriş yapan kullanıcılar
```

Örnek:

```text
Toplam kullanıcı: 1.000.000
Alışveriş yapan: 200.000
Churn olmuş: 60.000
```

Doğru hesap:

```text
60.000 / 200.000 = %30
```

Yanlış hesap:

```text
60.000 / 1.000.000 = %6
```

Çünkü hiç alışveriş yapmamış 800.000 kullanıcı zaten bu churn hesabının kitlesinde değildir.

---

# 22. Active Purchasers

Seçilen gün sınırını henüz aşmamış alışveriş yapan kullanıcılardır.

Örneğin sınır 90 günse ve kullanıcı son alışverişini 40 gün önce yaptıysa aktif sayılır.

Bu “kesin geri gelecek” anlamına gelmez.

Sadece henüz churn sınırını aşmadığını gösterir.

---

# 23. Churned Users

Son alışverişinden bu yana geçen süre seçilen sınırı aşmış kullanıcı sayısıdır.

Örneğin 90 günlük sınırda 110 gündür alışveriş yapmayan bir kullanıcı churn olur.

---

# 24. Churned One-Time Buyers

Sadece bir kez alışveriş yapmış ve sonra seçilen süre boyunca geri gelmemiş kullanıcılardır.

Bu grup genelde önemlidir çünkü şunu gösterir:

> İlk alışverişi yaptırıyoruz ama ikinci alışverişi getiremiyoruz mu?

Bu durum yeni müşteri kazanımı sonrası devamlılık problemi olabilir.

---

# 25. Churned Repeat Buyers

Daha önce birden fazla alışveriş yapmış ama sonra uzun süre geri gelmemiş kullanıcılardır.

Bu grup one-time müşterilerden farklı yorumlanmalıdır.

Çünkü bu kişiler daha önce alışkanlık göstermiştir.

Böyle bir kitlenin kaybı daha dikkat çekici olabilir.

---

# 26. Churned Revenue Share ne demek?

Bu değer churn olmuş kullanıcıların geçmişte ürettiği gelirin, bütün alışveriş yapan kullanıcıların geçmiş gelirine oranıdır.

Örnek:

```text
Churn rate = %25
Churned revenue share = %40
```

Bu durumda churn olmuş kullanıcılar sayıca %25 iken geçmiş gelirin %40'ını üretmiş olabilir.

Bu önemli bir işaret olabilir.

Ama bu değer:

```text
%40 gelir kaybettik
```

demek değildir.

Aynı şekilde:

```text
gelecekte %40 gelir kaybedeceğiz
```

de değildir.

Sadece bu kullanıcıların geçmişte ne kadar değer ürettiğini gösterir.

---

# 27. Status Diagnostics tablosu nasıl okunmalı?

Bu tabloda aktif, churn olmuş ve hiç alışveriş yapmamış kullanıcılar karşılaştırılır.

Genelde şu bilgiler yer alır:

- kullanıcı sayısı,
- ortalama alışveriş sayısı,
- ortanca alışveriş sayısı,
- ortalama gelir,
- ortanca gelir,
- son alışverişten bu yana geçen ortalama süre.

Burada ortalama ile ortanca değeri birlikte okumak önemlidir.

Örneğin:

```text
Ortalama gelir = 1.200 TL
Ortanca gelir = 300 TL
```

ise birkaç çok yüksek harcama yapan kullanıcı ortalamayı yukarı çekiyor olabilir.

Bu yüzden sadece ortalamaya bakmak yanlış izlenim verebilir.

---

# 28. Purchaser Status grafiği nasıl okunmalı?

Bu grafik aktif ve churn olmuş alışveriş yapan kullanıcı sayılarını yan yana gösterir.

Örnek:

```text
Aktif: 120.000
Churn: 80.000
```

Bu grafik doğrudan kullanıcı hacmini gösterir.

Yüzde görmek için ayrıca churn rate'e bakmak gerekir.

---

# 29. Churn Rate by Purchase Frequency grafiği nasıl okunmalı?

Kullanıcılar yaptıkları toplam alışveriş sayısına göre gruplara ayrılır:

```text
1 alışveriş
2 alışveriş
3–5 alışveriş
6+ alışveriş
```

Her grubun churn oranı ayrı hesaplanır.

Örnek:

```text
1 alışveriş   → %52 churn
2 alışveriş   → %34 churn
3–5 alışveriş → %19 churn
6+ alışveriş  → %10 churn
```

Bu bize şunu düşündürebilir:

> Daha sık alışveriş yapan kullanıcıların geri gelmeme oranı daha düşük.

Ama buradan:

```text
Bir kullanıcıya daha fazla alışveriş yaptırırsak churn kesin düşer
```

gibi bir sonuç çıkarılamaz.

Bu sadece iki durum arasında bir ilişki olduğunu gösterir.

---

# 30. Threshold Sensitivity grafiği ne işe yarıyor?

Bu grafik seçtiğimiz gün sayısının sonucu ne kadar değiştirdiğini gösterir.

Örneğin asıl seçimimiz 90 gün olsun.

Araç 60, 75, 90, 105, 120 gibi farklı günlerde churn oranını tekrar hesaplar.

Örnek:

```text
60 gün  → %36
75 gün  → %31
90 gün  → %27
105 gün → %24
120 gün → %21
```

Bu çok önemli bir kontroldür.

Çünkü churn oranı seçtiğimiz gün sayısına bağlıdır.

Eğer sonuçlar şöyleyse:

```text
75 gün  → %30
90 gün  → %29
105 gün → %28
```

seçilen gün sayısı biraz değişse bile sonuç çok değişmiyor demektir.

Ama şöyleyse:

```text
75 gün  → %42
90 gün  → %29
105 gün → %18
```

sonuç seçilen güne çok hassastır.

Bu durumda sadece “churn oranımız %29” demek yanıltıcı olabilir.

Daha doğru anlatım şudur:

> 90 günlük tanımda churn %29. 75 güne çekildiğinde %42, 105 güne çıkarıldığında %18 oluyor.

Böylece yöneticiler sonucun seçilen kurala bağlı olduğunu görür.

---

# 31. Gap Coverage ne demek?

Bu değer seçtiğimiz churn gününün geçmiş satın alma aralıklarının ne kadarını kapsadığını gösterir.

Örnek:

```text
Threshold = 90 gün
Gap coverage = %91
```

Bu şu demektir:

> Geçmişte gözlediğimiz alışveriş aralıklarının yaklaşık %91'i 90 gün veya daha kısa olmuş.

Bu, 90 günün mantıklı olup olmadığını değerlendirmede yardımcı olur.

Ama tek başına “90 gün kesin doğrudur” anlamına gelmez.

---

# 32. Churn süresi nasıl seçilmeli?

Bu araç churn süresini otomatik seçmez.

Çünkü her işin satın alma düzeni farklıdır.

Örneğin:

- market alışverişi yapan bir müşteri için 90 gün çok uzun olabilir,
- mobilya alan bir müşteri için 90 gün çok kısa olabilir,
- yıllık üyelikte 6 ay hiçbir şey ifade etmeyebilir,
- mevsimsel ürünlerde bazı aylar doğal olarak sessiz olabilir.

Bu yüzden karar verirken birlikte bakılması gerekenler şunlardır:

- median alışveriş aralığı,
- P75,
- P90,
- P95,
- alışveriş aralığı grafiği,
- 30/60/90 günlük kapsama oranları,
- farklı gün sınırlarında churn oranının nasıl değiştiği,
- işin gerçek satın alma döngüsü.

Örnek:

```text
Median = 28 gün
P75 = 48 gün
P90 = 83 gün
P95 = 125 gün
```

Bu durumda 60, 90 ve 120 gün gibi seçenekler karşılaştırılabilir.

Sonra işin yapısına en mantıklı olan seçilir.

---

# 33. HTML dashboard ne işe yarıyor?

`churn_analysis()` çalıştıktan sonra:

```text
ga4_churn_dashboard.html
```

oluşturulur.

Bu dosya sonuçların daha kolay paylaşılması için hazırlanır.

Dashboard'da özet olarak şunlar bulunur:

- seçilen churn günü,
- toplam alışveriş yapan kullanıcı,
- aktif kullanıcı,
- churn olmuş kullanıcı,
- churn oranı,
- seçilen günün alışveriş aralıklarının ne kadarını kapsadığı,
- churn olmuş kullanıcıların geçmiş gelir payı,
- kullanıcı gruplarının karşılaştırması,
- alışveriş sayısına göre churn oranı,
- farklı gün seçeneklerinde churn oranı.

Dashboard ayrı bir hesap yapmaz.

Notebook'taki sonuçları daha düzenli gösterir.

---

# 34. Sonuçları yorumlarken dikkat edilmesi gerekenler

## GA4 kullanıcı kimliği gerçek müşteri olmayabilir

`user_pseudo_id` cihaz ve tarayıcı bazlıdır.

Bu nedenle aynı kişi birden fazla kullanıcı gibi görünebilir.

Eğer şirketin sağlam bir `user_id` veya CRM müşteri kimliği varsa ileride analiz o seviyeye taşınabilir.

## Satın alma takibi hatalıysa churn sonucu da hatalı olur

Özellikle şunlar kontrol edilmelidir:

- `purchase` event'i doğru gönderiliyor mu?
- aynı sipariş iki kere gönderiliyor mu?
- gelir doğru geliyor mu?
- eski dönemlerde takip kesintisi var mı?

## Veri geçmişi çok kısa olabilir

Örneğin sadece son 3 aylık veri varsa 180 günlük churn hesabı yapmak mantıklı değildir.

Çünkü kullanıcıları yeterince uzun süre gözlemlememiş oluruz.

## Aktif görünen kullanıcı gelecekte churn olabilir

Bir kullanıcı son alışverişini 20 gün önce yaptıysa ve sınır 90 günse aktif görünür.

Ama bu kullanıcının gelecekte geri gelip gelmeyeceğini bilmiyoruz.

Bu araç geleceği tahmin etmez.

## Mevsimsellik dikkate alınmıyor

Bazı işler yılın belirli dönemlerinde yoğun olabilir.

Örneğin okul, tatil, kışlık ürün, yıllık yenileme gibi yapılarda satın alma aralıkları yıl içinde doğal olarak değişebilir.

Bu nedenle sonuç iş bilgisiyle birlikte değerlendirilmelidir.

---

# 35. Sonucu yöneticilere nasıl anlatmak daha doğru olur?

Tek başına:

```text
Churn oranı %27
```

demek yerine şu şekilde anlatmak daha sağlıklıdır:

```text
90 günlük churn tanımında alışveriş yapan kullanıcıların %27'si churn olmuş görünüyor.

Geçmiş alışveriş aralıklarının %90'ı yaklaşık 84 günün altında.
90 günlük sınır bu davranışın biraz üzerinde kalıyor.

75 gün seçersek churn oranı %31'e,
105 gün seçersek %24'e geliyor.

Tek alışveriş yapanlarda churn oranı daha yüksek,
6 ve üzeri alışveriş yapanlarda daha düşük.
```

Böyle bir anlatım hem sayıyı hem de sayının nasıl oluştuğunu açıklar.

---

# 36. Analizi paylaşmadan önce kısa kontrol listesi

- [ ] Doğru Google Cloud projesini kullandım mı?
- [ ] Doğru GA4 dataset'ini seçtim mi?
- [ ] Kaynak tablo doğru mu?
- [ ] Verinin son tarihi güncel mi?
- [ ] `purchase` takibi doğru mu?
- [ ] Gelir değerleri güvenilir mi?
- [ ] Yeterince uzun veri geçmişim var mı?
- [ ] Median alışveriş aralığına baktım mı?
- [ ] P75, P90 ve P95 değerlerini kontrol ettim mi?
- [ ] 30/60/90 günlük kapsama oranlarını gördüm mü?
- [ ] Farklı churn günlerinde sonuç ne kadar değişiyor baktım mı?
- [ ] Tek alışveriş yapanlarla tekrar alışveriş yapanları ayrı değerlendirdim mi?
- [ ] Churn olmuş kullanıcıların geçmiş gelir payını “kaybedilen gelir” diye sunmadım mı?
- [ ] `user_pseudo_id` değerinin gerçek müşteri sayısı olmadığını dikkate aldım mı?

---

# 37. En kısa haliyle bu analiz ne yapıyor?

Bütün akışı tek cümlede özetlersek:

> Kullanıcıların ne sıklıkla tekrar alışveriş yaptığını inceliyoruz, buna uygun bir gün sınırı seçiyoruz ve son alışverişinden beri bu sınırı geçen müşterileri churn olmuş olarak işaretliyoruz.

Akış şu:

```text
Önce maliyeti kontrol et
        ↓
Her kullanıcı için özet tablo oluştur
        ↓
Tekrar alışveriş yapanlar kaç günde bir geri geliyor bak
        ↓
Mantıklı bir gün sınırı seç
        ↓
Churn oranını hesapla
        ↓
Farklı gün sınırlarında sonucun ne kadar değiştiğini kontrol et
        ↓
Tek alışveriş yapanlarla sadık müşterileri ayrı ayrı yorumla
```

Bu araçtaki en önemli nokta churn oranının tek başına bir gerçek olmadığıdır.

Churn oranı, seçtiğimiz gün sınırına göre oluşur.

Bu yüzden en doğru kullanım şekli, churn oranını satın alma aralıkları ve farklı gün seçenekleriyle birlikte yorumlamaktır.
