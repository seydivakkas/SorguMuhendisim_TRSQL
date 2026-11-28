# TRSQL — Birleşik Araştırma Raporu: Türkçe Text-to-SQL Literatürü, Modeller, Mimari ve Açık Kaynak Ekosistemi

28 Kasım 2026 · Hazırlayan: Claude, Seydi için · Kaynak: Claude araştırma raporu (26–27 Kasım) + arkadaş raporu "Text-to-SQL Sistemleri Tasarımı: Literatür, Mimari Paradigmalar ve GitHub Ekosistemi" (28 Kasım)

> **Nasıl okunur.** Ana iskelet Claude raporudur (AS-01–AS-12, Türkçe veri kümeleri, RTX 4070 Laptop 8 GB kısıtı, lisans/KVKK, D0–D8). Arkadaş raporundan; semantik katman ve MCP (AS-06), SQLGlot dört şeritli guardrail (AS-10), karmaşıklığa göre yönlendirme (AS-09), benchmark güvenilirliği (AS-12) ve GitHub proje kataloğu (Ek A) eklendi.
>
> **İşaretler:** **(D)** birincil kaynağı açılıp okundu. **(B)** bellekten verildi, kaynağı bu turda açılmadı. **(A)** arkadaş raporundan alındı, bu turda doğrulanmadı. Yıldız sayıları ve liderlik tablosu skorları zamanla değişir; tezde kullanmadan önce kaynağından yeniden okuyun.
>
> Uygulama planı ayrı dosyadadır: `trsql-kodlama-plani.md`.

## Özet

8 GB kartlı yerel bir Türkçe Text-to-SQL prototipi için en makul başlangıç, Qwen3.5-9B tabanlı Hati-Glint-SQL-9B (Türkçe ince ayarlı) ile XiYanSQL-QwenCoder-7B ve Arctic-Text2SQL-R1-7B'nin Q4\_K\_M/Q5\_K\_M GGUF sürümlerini aynı harness'ta karşılaştırmaktır. Hepsi Apache 2.0.

- **Literatür:** Hakemli tek EN↔TR karşılaştırması BIRDTurk'te; Türkçe 12–15 puan düşüş, çok aşamalı işlem hattı Türkçede İngilizceden iki kat fazla kazandırıyor (+5,86 vs +2,68).
- **Modeller:** Türkçe skoru olan tek SQL modeli Hati-Glint-SQL-9B (TURSpider 73–78, BIRDTurk 47–55); skorlar yalnızca kendi kartında. İngilizce 7B lideri Arctic-R1-7B (BIRD dev 68,9).
- **Lisans:** Tek engel Qwen2.5-Coder-3B (`qwen-research`); bu tabandan türeyen XiYanSQL-3B de risk taşır.
- **Donanım:** RTX 4070 Laptop 8 GB (teyit edildi), net bütçe ≈6,8–7,0 GB. 7–9B modeller Q4/Q5 ile 8–16K bağlamda sığar; 14B sığmaz.
- **Boşluk:** Kurumsal, Türkçe değerli, iş kuralı içeren bir ölçüt ve küçük modelde RAG + doğrulama ablasyonu literatürde yok; hipotez bu noktada özgün.

**27 Kasım güncellemesi:** Seydi'nin paylaştığı literatür raporuyla karşılaştırıldı. Donanım ve D0–D8 tanımları rapora işlendi. İki düzeltme yapıldı: BIRDTurk'ün HF lisansı CC BY-NC-SA 4.0 (ticari eğitim yok) ve HF'deki şemalar Türkçe. Jin vd. (2026) etiket hatası bulgusu Bölüm 8'e eklendi.

### Plan iyileştirme önerileri

1. **D3 ve D5'i bileşenlerine ayırın.** Revize D0–D8 planı (Bölüm 8.1) kümülatif; birden fazla bileşen taşıyan kademelerde leave-one-out koşuları olmadan tek bileşenin katkısı ölçülemez.
2. **İlk deneyi "bağımsız yeniden ölçüm" yapın.** Adayları aynı istem, aynı nicemleme ve aynı değerlendiriciyle TURSpider + BIRDTurk dev'de ölçmek, hem AS-03'ün doğrulama hedefini karşılar hem de sonraki ablasyonların taban çizgisini verir.
3. **Abstention / Clarification metriği ekleyin.** Belirsiz ve yanıtsız soruları veri kümesine koymak, metrik olmadan ölçülemez.
4. **BIRDTurk'ü yalnızca değerlendirmede kullanın.** HF lisansı CC BY-NC-SA 4.0; D7 ince ayar verisine girmemeli.
5. **TUR2SQL'i ana ölçüt yapmayın.** %96–98 EX ile ayırt edici değil; yalnızca tarihsel karşılaştırma için.
6. **Lisanssız veri kümeleri için izin alın.** TURSpider ve TUR2SQL'de lisans beyanı yok.

## Araştırma sorularına kısa yanıtlar (AS-01 – AS-12)

Her yanıtın kanıtı parantez içinde gösterilen bölümdedir. (D) birincil kaynağı okunmuş, (B) bellekten verilmiş bilgidir.

**AS-01 — Text-to-SQL alanında hangi yöntemler geliştirilmiştir?** Alan beş dönemden geçti: kural/dilbilgisi tabanlı sistemler, seq2seq ve iskelet modelleri (Seq2SQL, SQLNet, RAT-SQL), önceden eğitilmiş kodlayıcı-çözücüler (T5 + PICARD, RESDSQL), LLM ile bağlam içi öğrenme (DIN-SQL, DAIL-SQL) ve çok ajanlı / çok adaylı sistemler (CHESS, CHASE-SQL, XiYan-SQL). 2025–2026'nın belirleyici gelişmesi, çalıştırma doğruluğunu ödül olarak kullanan GRPO eğitimi ve milyonluk sentetik veridir: Arctic-Text2SQL-R1-7B BIRD dev'de 68,9, OmniSQL-7B 63,9 EX'e ulaşıyor (D). Kurumsal gerçekliği ölçen Spider 2.0'da ise 7B modeller %10–16 bandında kalıyor (Bölüm 1(a), 1(b)).

**AS-02 — Türkçe Text-to-SQL için mevcut akademik çalışmalar nelerdir?** Üç birincil veri kümesi var, üçü de İngilizceden çeviri: TUR2SQL (UBMK 2023, 10.809 çift; ChatGPT test EX 98,38, yani doymuş), TURSpider (IEEE Access 2024, Spider'ın insan çevirisi, şema ve değerler İngilizce) ve BIRDTurk (SIGTURK 2026, 10.962 çift, şema Türkçe, hücre değerleri İngilizce). Hakemli tek EN↔TR karşılaştırması BIRDTurk'te: aynı modelde Türkçe 12–15 puan düşüş (D). Gerçek Türkçe kurumsal soru içeren bir veri kümesi bulunamadı (Bölüm 1(b), 2(b)).

**AS-03 — Hangi açık ağırlıklı küçük modeller Türkçe SQL üretmeye uygundur?** 8 GB VRAM ve ticari lisans koşuluyla üç aday öne çıkıyor: Hati-Glint-SQL-9B (Türkçe ince ayarlı; TURSpider 73–78, BIRDTurk 47–55, yalnızca kendi kartında), Arctic-Text2SQL-R1-7B (BIRD dev 68,9) ve XiYanSQL-QwenCoder-7B (BIRD dev 62,1). Hepsi Apache 2.0. İngilizce SQL modellerinin hiçbiri Türkçede bağımsız ölçülmemiş; uygunluk iddiası ancak aynı değerlendirme düzeneğinde TURSpider + BIRDTurk dev ile yeniden ölçülerek kurulabilir. 4B sınıfında Qwen3-4B-Instruct-2507 hafif alternatif (Bölüm 2(a), 2(b)).

**AS-04 — Küçük modellerin doğruluğu RAG ile artırılabilir mi?** Evet, ama kazanç düz metin RAG'ından değil, veritabanına özgü bileşenlerden gelir: şema getirimi ve budama, doğrulanmış örnek SQL (few-shot), iş kuralı / evidence ve değer eşleme. En güçlü Türkçe kanıt: şema bağlama ve öz-düzeltme içeren DIN-SQL, BIRDTurk'te ICL'ye göre +5,86 puan kazandırıyor, İngilizcede yalnızca +2,68 (D). 3B–9B modellerde bileşen bazında Türkçe ablasyon yayımlanmamış; D0–D8 planı tam olarak bunu ölçer (Bölüm 4(b), 8(a)).

**AS-05 — Veritabanı şeması en verimli şekilde nasıl temsil edilir?** Aynı modelde M-Schema (sütun tipi + açıklama + örnek değer + yabancı anahtar), düz DDL'e göre BIRD dev'de 3B'de +3,0, 7B'de +4,7, 32B'de +4,9 puan kazandırıyor (D). Büyük şemalarda önerilen sıra: yüksek recall'lu budama (hedef ≥ %95), FK grafıyla JOIN yolu tamamlama, sonra M-Schema serileştirme. JSON/YAML temsilinin etkisini ölçen bir kaynak bulunamadı; açık soru (Bölüm 4(a)).

**AS-06 — Kuruma özgü iş kuralları modele nasıl aktarılabilir?** En güvenilir yol, "ciro", "iade", "aktif müşteri" gibi tanımları SQL parçacığı + açıklama olarak bir anlamsal katmanda tutup soruyla eşleşenleri BIRD'deki *evidence* gibi isteme eklemektir; eş anlamlı listesi (ciro / hasılat / satış tutarı) aynı katmanda durur. Sık sorulan KPI'lar için LLM'e hiç bırakılmayan sabit, doğrulanmış sorgular (semantik katman) daha güvenlidir. İş kurallarını ince ayarla öğretmek, kural değiştiğinde yeniden eğitim gerektirdiği için önerilmez (Bölüm 4(b), 5(a)).

**AS-07 — Fine-tuning hangi koşullarda gereklidir?** Önce RAG + doğrulama ile tavan ölçülmeli. İnce ayar yalnızca üç durumda gerekir: Türkçe soru anlama zayıflığı (Hati'de LoRA SFT Türkçede +7–9 puan getirdi (D)), RAG ve transpile ile düzelmeyen kalıcı lehçe hataları, çok düşük gecikme için 3–4B modeli özelleştirme. Bedeli: genel yetenekte küçük kayıp (Hati'de TurkishMMLU −1,1) ve şema/taban değişince yeniden eğitim. GRPO/DPO çoklu GPU ister; 8 GB dizüstünde gerçekçi değil. BIRDTurk lisansı (CC BY-NC-SA) ticari ince ayar verisinde kullanımı engeller (Bölüm 5(a)).

**AS-08 — SQL üretiminde halüsinasyonlar nasıl azaltılabilir?** Katmanlı bir sıra öneriliyor: SQLGlot ile AST ayrıştırma ve şemaya karşı tanımlayıcı kontrolü (var olmayan tablo/sütunu kesin yakalar), hata mesajıyla 1–2 tur onarım, zaman el veriyorsa çoklu aday + sonuç oylaması. Oylama sqrl-9b'de BIRD dev'i 66,6'dan 69,8'e çıkardı (D). GBNF kısıtlı çözme geçersiz SQL'i sıfırlar ama anlamsal hatayı düzeltmez; thinking modellerinde yalnızca son SQL bloğuna uygulanmalı (Bölüm 5(b)).

**AS-09 — Düşük donanımda doğruluk ve hız dengesi nasıl kurulur?** RTX 4070 Laptop 8 GB'ta net bütçe ≈6,8–7,0 GB. 7–9B modeller Q4\_K\_M/Q5\_K\_M ile 8–16K bağlamda tamamen GPU'da çalışır; 14B sığmaz. 7B sınıfında 4-bit nicemleme kod doğruluğunu pratikte düşürmüyor (Qwen2.5-Coder-7B, BigCodeBench: FP16 0,41, AWQ 0,41, GGUF 0,40 (D)); 3–4B'de ise Q4 biçim hatasını artırdığı için Q5/Q6 seçilmeli. Gömme modeli CPU'ya, KV cache q8\_0'a alınır. Tek kullanıcıda llama.cpp yeterli; tahmini hız 7B Q4'te \~35–40 tok/sn. Bu kartta ölçülmüş P50/P95 verisi yok (Bölüm 6(a), 6(b)).

**AS-10 — Kurumsal veritabanlarında güvenli sorgulama nasıl sağlanır?** LLM çıktısı güvenilmeyen girdi sayılır ve güvenlik veritabanında zorlanır: yalnızca SELECT yetkili salt okunur rol, AST düzeyinde DDL/DML ve tehlikeli fonksiyon reddi, rol bazında tablo/sütun izin listesi, PostgreSQL RLS, kişisel veri sütunları için maskeli görünümler. Ağır sorgulara karşı EXPLAIN ön maliyet eşiği, `statement_timeout` (ör. 10 sn), zorunlu `LIMIT` ve korelasyon kimlikli denetim kaydı (B). Başarı ölçütü: DB'ye ulaşan tehlikeli SQL oranı %0 (Bölüm 7(a), 7(b)).

**AS-11 — Modellerin ticari kullanım koşulları nelerdir?** Adayların neredeyse tümü Apache 2.0 (ticari kullanım, ince ayar ve dağıtım serbest; LICENSE ve NOTICE korunur). İstisna Qwen2.5-Coder-3B (`qwen-research`, ticari kullanım ayrıca izin ister); bu tabandan türeyen XiYanSQL-3B de bu riski taşır. Veri tarafta BIRDTurk HF kartında CC BY-NC-SA 4.0 (ticari eğitim yok); TUR2SQL'de lisans beyanı yok. Yerel çalışma, KVKK md. 9 kapsamındaki yurt dışı aktarım riskini kaldırır (Bölüm 3(a), 3(b)).

**AS-12 — Türkçe Text-to-SQL alanındaki araştırma boşlukları nelerdir?** Altı boşluk saptandı: (1) iş kuralı içeren, Türkçe şemalı ve Türkçe değerli kurumsal ölçüt yok; (2) ekli Türkçe değerlerin eşlenmesi hiç ölçülmemiş; (3) Türkçede belirsiz ve yanıtsız soru verisi yok; (4) 3–9B modellerde RAG + doğrulama bileşimine dair tekrarlanabilir ablasyon yok; (5) nicemlemenin SQL doğruluğuna etkisi çalışılmamış; (6) Türkçe SQL modellerinin skorları bağımsız doğrulanmamış. Ayrıca BIRD'deki yaygın etiket hataları (Mini-Dev'in %52,8'i (D)) BIRDTurk'e de taşınıyor. Tez hipotezi 1, 2, 4 ve 5'i aynı anda hedeflediği için özgün (Bölüm 8(b)).

## 1. Yöntemlerin evrimi, ölçütler ve Türkçe veri kümeleri (AS-01, AS-02)

Alanın ağırlık merkezi 2023'ten bu yana ince ayarlı seq2seq modellerden, LLM tabanlı ve çalıştırma geri beslemeli işlem hatlarına kaydı. Türkçede ise yalnızca üç birincil veri kümesi var ve gerçek kurumsal Türkçe soru içeren hiçbiri yok.

**Kaynak notu:** (D) işaretli bilgiler bu çalışmada birincil kaynaktan açılıp okundu. (B) işaretliler alanın iyi bilinen yayınlarıdır, künyeleri bellekten verildi ve bu turda sayfaları açılmadı; tezde kullanmadan önce künyeyi doğrulayın.

### 1(a) Yöntemsel evrim ve SOTA mimariler

| Dönem | Temsilci çalışmalar | Temel fikir | Kalıcı katkısı |
| --- | --- | --- | --- |
| Kural / dilbilgisi tabanlı (≤2016) | NaLIR, ATHENA (B) | Ayrıştırma ağacı + elle kurallar | Açıklanabilirlik; bugün değer normalizasyonunda yaşıyor |
| Seq2seq / sketch (2017–2020) | [WikiSQL / Seq2SQL](https://arxiv.org/abs/1709.00103), SQLNet, IRNet, RAT-SQL (B) | Kodlayıcı-çözücü, şema-soru ilişki kodlaması | Schema linking kavramı |
| Önceden eğitilmiş seq2seq (2021–2022) | T5 + [PICARD](https://arxiv.org/abs/2109.05093), [RESDSQL](https://arxiv.org/abs/2302.05965) (B) | Kısıtlı kod çözme, şema sıralama + ayrıştırma | Constrained decoding, şema budama |
| LLM bağlam içi öğrenme (2023) | [DIN-SQL](https://arxiv.org/abs/2304.11015), [DAIL-SQL](https://arxiv.org/abs/2308.15363) (B) | Ayrıştırılmış istem, benzer örnek seçimi, öz-düzeltme | Few-shot RAG, aşamalı istem |
| Çok ajanlı / çok aday (2024–2025) | [CHESS](https://arxiv.org/abs/2405.16755), [CHASE-SQL](https://arxiv.org/abs/2410.01943), [XiYan-SQL](https://arxiv.org/abs/2411.08599) (B) | Değer/şema alıcı ajanları, çok üreteçli aday + seçici model | Aday üretip seçme, LSH değer eşleme |
| Akıl yürütme + RL (2025–2026) | [Arctic-Text2SQL-R1](https://arxiv.org/abs/2505.20315), [OmniSQL](https://arxiv.org/abs/2503.02240) (D) | GRPO ile çalıştırma ödülü; milyonluk sentetik veri | Küçük modelde büyük model düzeyi doğruluk |

### 1(b) Uluslararası ölçütler

| Ölçüt | Ne ölçer | Not |
| --- | --- | --- |
| WikiSQL (2017) (B) | Tek tablo, basit SELECT | Doymuş; tez için yalnızca tarihsel |
| [Spider](https://arxiv.org/abs/1809.08887) (2018) (B) | Çapraz alan, çok tablolu; EM + EX + Test Suite | Açık modeller test EX'te %85–89 bandında (bkz. Bölüm 2) |
| [BIRD](https://arxiv.org/abs/2305.03111) (2023) (B) | Büyük, kirli değerli gerçek veritabanları + dış bilgi (evidence); EX + VES | 95 veritabanı; küçük modellerin gerçek ayırt edildiği ölçüt |
| [Spider 2.0](https://arxiv.org/abs/2411.07763) (2024) (B) | Kurumsal iş akışı: BigQuery/Snowflake, yüzlerce sütun, çok adımlı | 7B modellerde tek haneli/düşük iki haneli skorlar (Arctic-R1-7B: Spider2.0-DK %15,6 (D)) |

### 1(b) Türkçe veri kümeleri: çeviri-uyarlama, çalıştırma anlamı ve başarı oranları

| Veri kümesi | Künye | Boyut | Uyarlama yöntemi | Raporlanan başarı | Lisans |
| --- | --- | --- | --- | --- | --- |
| [TUR2SQL](https://research.itu.edu.tr/en/publications/tur2sql-a-cross-domain-turkish-dataset-for-text-to-sql/) (D) | Kanburoğlu & Tek, UBMK 2023, DOI 10.1109/UBMK59864.2023.10286686 | 10.809 soru-SQL çifti | Özetinde belirtilmiyor | Test EX: SQLNet 40,19; ChatGPT 98,38; SQLCoder (şemalı) 97,04 ([GitHub](https://github.com/alibugra/TUR2SQL)) | Depoda lisans yok |
| [TURSpider](https://research.itu.edu.tr/en/publications/turspider-a-turkish-text-to-sql-dataset-and-llm-based-study/) (D) | Kanburoğlu & Tek, IEEE Access 12 (2024) 169379–169387, DOI 10.1109/ACCESS.2024.3498841 | Spider ile aynı yapı (sayı özetinde yok) | Spider'ın insan çevirisi | Özette sayı yok; ince ayarlı bir Türkçe LLM'nin EX'te GPT-3.5/4'ü geçtiği, Chain-of-Feedback kullanıldığı belirtiliyor | Seydi'nin paylaştığı rapora göre HF kartında CC BY 4.0 (bu turda açılmadı) |
| [BIRDTurk](https://aclanthology.org/2026.sigturk-1.13/) (D) | Aktaş vd. (Roketsan + ODTÜ), SIGTURK 2026 @ EACL, s. 155–171 | 10.962 çift (9.428 train, 1.534 dev; test yok) | Gemini-2.5-flash ile şema eşleme sözlüğü; soru+evidence ortak çeviri; SQL'de yalnızca AST üzerinde tablo/sütun düğümleri yeniden adlandırıldı; **hücre değerleri çevrilmedi** | Gemini-2.5-flash-lite dev EX: ICL EN 58,21 → TR 43,16; DIN-SQL EN 60,89 → TR 49,02. İnce ayarlı Qwen2.5-Coder-3B: 15,38 | Makale: CC BY-SA 4.0; HF veri kartı: CC BY-NC-SA 4.0 ([depo](https://github.com/metunlp/birdturk)) |

**Çalıştırma anlamının korunması.** BIRDTurk, her örnekte İngilizce ve Türkçe SQL'i aynı veritabanında çalıştırıp sonuç kümelerinin özdeş olmasını şart koşuyor. 974 örneklik insan kontrolünde %98,15 doğru çeviri raporlanıyor. Bu oran çeviri doğruluğudur, çalıştırma eşdeğerliği oranı değildir; otomatik kontrolden kaç örneğin düştüğü raporlanmamış.

**TUR2SQL skorlarına dikkat.** %96–98 EX değerleri veri kümesinin kolay olduğunu, tez için ayırt edici olmadığını gösteriyor. "Şemasız SQLCoder 96,48" satırı şema bilgisi olmadan bu skora ulaşılması nedeniyle şema sızıntısı / ezber şüphesi taşır.

**Açık bulgu:** 2025–2026'da TURSpider/BIRDTurk dışında hakemli yeni bir Türkçe Text-to-SQL veri kümesi bu taramada bulunamadı. Çok dilli tarafta MultiSpider gibi çalışmalar Türkçeyi kapsamıyor (B, doğrulanmalı).

## 2. Model envanteri ve skor doğrulaması (AS-03)

Türkçe skoru olan tek SQL modeli Hati-Glint-SQL-9B; o da yalnızca kendi raporladığı skorlara sahip. İngilizce SQL'de 7B sınıfının lideri Arctic-Text2SQL-R1-7B (BIRD dev 68,9). Türkçede bu modellerin hiçbiri bağımsız olarak ölçülmemiş; tezin ilk deneyi bu boşluğu kapatmalı.

### 2(a) Aday modeller: boyut, bağlam, mimari ve eğitim verisi

| Model | Boyut (HF alanı) | Taban | Bağlam | Türkçe | Lisans (kart) |
| --- | --- | --- | --- | --- | --- |
| [XiYanSQL-QwenCoder-3B-2504](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-3B-2504) | 3B | Qwen2.5-Coder-3B | Kartta yok; taban 32K | Hayır (İng./Çin.) | apache-2.0 |
| [XiYanSQL-QwenCoder-7B-2504](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-7B-2504) | 8B | Qwen2.5-Coder-7B | Kartta yok; taban 128K | Hayır | apache-2.0 |
| XiYanSQL-QwenCoder-14B-2504 | 14B | Qwen2.5-Coder-14B | — | Hayır | Kartı açılmadı |
| [XiYanSQL-QwenCoder-32B-2504](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-32B-2504) | 33B | Qwen2.5-Coder-32B | Kartta yok | Hayır | apache-2.0 |
| [OmniSQL-7B](https://huggingface.co/seeklhy/OmniSQL-7B) / 14B / [32B](https://huggingface.co/seeklhy/OmniSQL-32B) | 8B / 14B / 33B | Qwen2.5-Coder (makale) | Örnek kodda 8K | Hayır | apache-2.0 (7B, 32B) |
| [Arctic-Text2SQL-R1-7B](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B) | 8B | Qwen2.5-Coder-7B-Instruct | Kartta yok | Hayır | apache-2.0 |
| [Qwen2.5-Coder-7B-Instruct](https://qwenlm.github.io/blog/qwen2.5-coder-family/) | 7B | — | 128K | Genel çok dilli | Apache 2.0 |
| [Qwen2.5-Coder-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct) | 3,09B | — | 32K | Genel çok dilli | **qwen-research** |
| [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | 4,0B | — | 262K | Çok dilli (dil listesi yok) | apache-2.0 |
| [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | 10B (9B LM + görme) | Qwen3.5-9B-Base | 262K (1M'a uzatılabilir) | "201 dil"; Türkçe adıyla geçmiyor | apache-2.0 |
| [Hati-Glint-SQL-9B-v1](https://huggingface.co/runelab-ai/Hati-Glint-SQL-9B-v1) | 10B | Qwen3.5-9B (LoRA SFT) | Kartta yok | Evet (birincil) | apache-2.0 + NOTICE |
| [Trendyol-LLM-8B-T1](https://featherless.ai/models/Trendyol/Trendyol-LLM-8B-T1/readme) | 8B | Qwen3-8B | 32K | Evet (e-ticaret) | Apache-2.0 |
| [sqrl-9b](https://huggingface.co/feyninc/sqrl-9b) (ek aday) | 10B | Qwen3.5-9B, RL | Kartta yok | Hayır | apache-2.0 |

**Mimari notu.** Qwen3.5-9B hibrit dikkat kullanıyor: 32 katmanın her 4'ünden 3'ü Gated DeltaNet (doğrusal dikkat), 1'i tam dikkat ([kart](https://huggingface.co/Qwen/Qwen3.5-9B)). Bu, KV cache'in yalnızca tam dikkat katmanlarında büyümesi demek; uzun şema bağlamında 8 GB kartta avantajlı olabilir. llama.cpp/Ollama'daki desteğin olgunluğu ayrıca test edilmeli. Hati ve sqrl bu tabanı miras alıyor.

**Eğitim verisi ve yöntemi.**

| Model | Eğitim yöntemi | Eğitim verisi | Kaynak |
| --- | --- | --- | --- |
| OmniSQL 7B/14B/32B | Tam SFT, CoT çıktılı | SynSQL-2.5M: 2.544.390 örnek, 16.583 sentetik DB; her örnek ⟨DB, soru, SQL, CoT⟩; 9 farklı soru üslubu (resmi, günlük, belirsiz vb.) | [Makale](https://arxiv.org/html/2503.02240v2) (D) |
| Arctic-Text2SQL-R1-7B | GRPO; ödül: doğru sonuç 1, çalışan SQL 0,1, diğer 0 | BIRD + Spider eğitim kümeleri ve filtrelenmiş sentetik veri | [Makale](https://arxiv.org/abs/2505.20315) (ödül D, veri ayrıntısı B) |
| XiYanSQL-QwenCoder-2504 | Çok üreteçli SFT, M-Schema biçimi | Kartında ayrıntı yok; SQLite, PostgreSQL, MySQL lehçeleri | [Kart](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-7B-2504) (D) |
| Hati-Glint-SQL-9B | Qwen3.5-9B üzerine LoRA SFT (Gated DeltaNet projeksiyonları dahil) | Türkçe SQL verisi; kaynak ve boyutu kartta açık değil | [Kart](https://huggingface.co/runelab-ai/Hati-Glint-SQL-9B-v1) (D) |
| sqrl-9b | SFT + RL, çok adımlı keşif (öğretmen: Qwen3.6-35B-A3B) | BIRD dev ve Spider test eğitimde kullanılmamış | [Kart](https://huggingface.co/feyninc/sqrl-9b) (D) |
| Trendyol-LLM-8B-T1 | Qwen3-8B üzerine Türkçe e-ticaret ince ayarı | SQL'e özgü değil | [README](https://featherless.ai/models/Trendyol/Trendyol-LLM-8B-T1/readme) (D) |

### 2(b) Skorların çapraz doğrulanması ve protokol farkları

| Model | BIRD dev EX | Spider test EX | Spider 2.0 | TURSpider dev EX | BIRDTurk dev EX | Kaynak türü |
| --- | --- | --- | --- | --- | --- | --- |
| XiYanSQL-3B | 55,08 (M-Schema) / 52,09 (DDL) | 84,10 / 80,57 | — | — | — | Kendi kartı |
| XiYanSQL-7B | 62,13 / 57,43 | 85,97 / 82,48 | — | — | — | Kendi kartı |
| XiYanSQL-32B | 67,14 / 62,26 | 89,20 / 86,17 | — | — | — | Kendi kartı |
| OmniSQL-32B | 60,37 / 55,87 | 85,16 / 83,19 | — | — | — | XiYan kartı (rakip ölçümü) |
| OmniSQL-7B/14B | Kartta yalnızca görsel | — | Spider2.0-SQLite (görsel) | — | — | Sayılar [makalede](https://arxiv.org/abs/2503.02240); bu turda okunmadı |
| Arctic-Text2SQL-R1-7B | 68,9 (test 68,5) | 88,8 | Spider2.0-DK 15,6 | — | — | Kendi kartı + makale |
| sqrl-9b | 66,6 pass@1; 69,8 (8 oy) | — | — | — | — | Kendi kartı, ajanlı çok adım |
| Qwen3.5-9B (taban) | \~56 (sqrl düzeneği) | — | — | 64,12 | 40,09 | Hati ve sqrl kartları |
| Hati-Glint-SQL-9B | — | — | — | 73,21 (direkt) / 76,79 (thinking) / 77,85 (ajan) | 47,26 / 54,37 / 55,35 | Kendi kartı, %95 Gİ verilmiş |
| Trendyol-LLM-8B-T1 | — | — | — | 61,61 | 29,86 (en iyi 34,29) | Hati kartı (rakip ölçümü) |
| Gemini-2.5-flash-lite (referans) | EN ICL 58,21 | — | — | — | 43,16 (ICL) / 49,02 (DIN-SQL) | BIRDTurk makalesi (hakemli) |
| Qwen2.5-Coder-3B (BIRDTurk SFT) | — | — | — | — | 15,38 | BIRDTurk makalesi |

**Doğrulanamayanlar.** Qwen2.5-Coder-7B ve Qwen3-4B için resmi kartlarda Spider/BIRD skoru yok; bu modeller için dolaşan sayılar üçüncü taraf tablolarından gelir. XiYanSQL-14B ve OmniSQL-14B kartları bu turda açılmadı. Arctic-Text2SQL-R1'in 14B/32B sürümlerinin açık ağırlık olarak yayınlanıp yayınlanmadığı doğrulanmadı. Plandaki "Qwen3.5 (9B)" gerçek bir sürüm ve resmi kartı mevcut.

**OmniSQL makalesinden (greedy, %):** Bu değerler, Seydi'nin paylaştığı rapordaki OmniSQL-7B sayılarıyla (Spider test 87,9, BIRD dev 63,9) örtüşüyor. Ayrıca Qwen2.5-Coder-7B-Instruct için yayımlanmış tek bağımsız taban çizgisi bu tablodur ([makale](https://arxiv.org/html/2503.02240v2); tablo özetten okundu, alıntılamadan önce PDF'ten kontrol edin).

| Model | Spider dev | Spider test | BIRD dev | Spider2.0-SQLite |
| --- | --- | --- | --- | --- |
| Qwen2.5-Coder-7B-Instruct | 73,4 | 82,2 | 50,9 | 1,5 |
| OmniSQL-7B | 81,2 | 87,9 | 63,9 | 10,4 |
| OmniSQL-14B | 81,4 | 88,3 | 64,2 | 10,4 |
| OmniSQL-32B | 80,9 | 87,6 | 64,5 | 11,9 |

Çıkarım: 7B'den 32B'ye çıkmak OmniSQL'de BIRD dev'de yalnızca +0,6 puan getiriyor. 8 GB sınırında 14B/32B'nin olmaması doğruluk açısından büyük kayıp değil.

**Protokol farkları (skorları doğrudan kıyaslamayın).**

- XiYan skorları şema biçimine 3–5 puan duyarlı (M-Schema vs DDL).
- Arctic ve XiYan tek aday (greedy); sqrl 8 adaylı oylama ve çok adımlı keşif; Hati "ajan" modu çalıştırma geri beslemesi kullanıyor.
- Spider skorları test kümesinde (XiYan, Arctic) veya dev kümesinde test-suite (OmniSQL) raporlanıyor.
- BIRD dev 1.534 soru; BIRDTurk dev aynı 1.534 sorunun çevirisi. Bu nedenle EN↔TR farkı doğrudan ölçülebilir.

### 2(b) BIRDTurk başarı düşüşünün teknik nedenleri

Hakemli tek kanıt BIRDTurk makalesi: aynı model ve yöntemde EN→TR düşüş ICL'de 15,1, DIN-SQL'de 11,9 puan. Çok aşamalı yöntem (schema linking + öz-düzeltme) Türkçede ICL'ye göre +5,86, İngilizcede yalnızca +2,68 kazandırdı. Yani yapılandırılmış işlem hattı Türkçede daha değerli; bu, tez hipotezini destekleyen en güçlü mevcut veri noktası.

Makalenin önerdiği nedenler (ablasyonla izole edilmemiş): SOV söz dizimi ve eklerin SQL operatörlerine dağılması ("-den büyük"), tip/token oranının yaklaşık iki katına çıkması, evidence token sayısında %2,6–9,3 artış, Türkçenin ön eğitimde az temsili. Ek bir neden: **hücre değerleri İngilizce kaldığı için** Türkçe soru ile İngilizce değer arasında diller arası value linking gerekiyor; bu gerçek Türk kurumsal veritabanlarında olmayacak yapay bir zorluk.

**Sürüm ve lisans uyarısı.** HF'deki [`metunlp/birdturk` dev dosyası](https://huggingface.co/datasets/metunlp/birdturk/blob/main/dev/dev_tr.json) Türkçe tablo/sütun adları içeriyor (ör. `okullar`, `sehir`, `kaliforniya_okullari`); yani makale doğru, GitHub README'deki "şemalar İngilizce kalır" ifadesi eskimiş. README'deki 12.751 sayısı orijinal BIRD'ün toplamıdır; yayımlanan BIRDTurk 10.962 çifttir. **Lisans çelişkili:** makale CC BY-SA 4.0 diyor, HF veri kartı `cc-by-nc-sa-4.0` gösteriyor. Daha kısıtlayıcı olan NC (ticari olmayan) koşulu esas alınmalı: BIRDTurk yalnızca değerlendirmede kullanılmalı, ticari ince ayar verisine girmemeli.

## 3. Lisans matrisi ve on-prem / KVKK (AS-11)

Aday listesindeki tek ticari engel Qwen2.5-Coder-**3B**'nin `qwen-research` lisansıdır; aynı ailenin 0.5B, 1.5B, 7B, 14B ve 32B sürümleri Apache 2.0'dır ([Qwen blog tablosu](https://qwenlm.github.io/blog/qwen2.5-coder-family/), [3B kartı](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct)). Diğer tüm adayların kartları apache-2.0 etiketli.

### 3(a) Ticari üretim, ince ayar, dağıtım ve atıf koşulları

| Model | Lisans | Ticari üretim | İnce ayar + dağıtım | Atfı / koşul | Dikkat |
| --- | --- | --- | --- | --- | --- |
| Qwen2.5-Coder 0.5B/1.5B/7B/14B/32B | Apache 2.0 | Evet | Evet | LICENSE + NOTICE korunur, değişiklik belirtilir | — |
| Qwen2.5-Coder-3B | Qwen Research | **Ticari kullanım için ayrı izin gerekir** (lisans metnine göre doğrulayın) | Araştırma amaçlı | — | Prototipte kullanılabilir, üründe kullanılamaz |
| XiYanSQL-QwenCoder-3B-2504 | apache-2.0 (kart) | Kart açısından evet | Evet | Apache koşulları | **Tabanı research lisanslı Qwen2.5-Coder-3B.** Türev eser lisansı tabanın kısıtını kaldıramaz; hukuki görüş alınmadan ticari üründe kullanmayın |
| XiYanSQL 7B / 32B (14B doğrulanmadı) | apache-2.0 | Evet | Evet | Apache | — |
| OmniSQL 7B / 32B (14B doğrulanmadı) | apache-2.0 | Evet | Evet | Apache | Eğitim verisi SynSQL-2.5M lisansı ayrıca kontrol edilmeli |
| Arctic-Text2SQL-R1-7B | apache-2.0 | Evet | Evet | Apache | — |
| Qwen3-4B-Instruct-2507, Qwen3.5-9B | apache-2.0 | Evet | Evet | Apache | — |
| Hati-Glint-SQL-9B-v1 | apache-2.0 + NOTICE | Evet | Evet | NOTICE dosyasındaki atfılar korunmalı (dosya açılmadı) | Kart: yalnızca SQLite, salt okunur bağlantı |
| Trendyol-LLM-8B-T1 | Apache-2.0 (Featherless kopyası) | Evet | Evet | Apache | Eski [Llama-3 tabanlı Trendyol sürümleri](https://huggingface.co/Trendyol/Llama-3-Trendyol-LLM-8b-chat-v2.0/discussions/1) Llama 3 lisansına tabidir (adında "Llama" ve "Built with Llama" koşulu). HF üzerindeki LICENSE dosyasından teyit edin |
| sqrl-9b | apache-2.0 | Evet | Evet | Apache | Öğretmen modeli Qwen3.6-35B-A3B; distilasyon koşulları ayrıca okunmalı |

**Veri kümesi lisansları:** BIRD CC BY-SA 4.0. BIRDTurk için makale CC BY-SA 4.0, [HF veri kartı](https://huggingface.co/datasets/metunlp/birdturk/blob/main/dev/dev_tr.json) ise CC BY-NC-SA 4.0 diyor; NC koşulu esas alınmalı, yani yalnızca değerlendirme, ticari eğitim yok. TURSpider için Seydi'nin paylaştığı rapor HF kartında CC BY 4.0 bildiriyor (bu turda doğrulanmadı). TUR2SQL deposunda lisans yok; yazarlardan yazılı izin önerilir.

### 3(b) On-premise / air-gapped barındırma, veri aktarım riski ve KVKK

Yerel ağırlıklı mimari, KVKK açısından asıl riski (yurt dışına veri aktarımı, 6698 sayılı Kanun md. 9) ortadan kaldırır; ancak tek başına uyum sağlamaz (B; mevzuat metnini [mevzuat.gov.tr](https://www.mevzuat.gov.tr) üzerinden doğrulayın).

Seydi'nin paylaştığı rapor iki güncel dayanak ekliyor: 7499 sayılı Kanun (12 Mart 2024) ile değişen md. 9 aktarım rejimi (yeterlilik kararı → standart sözleşme/BCR → arızi istisna; standart sözleşmenin 5 iş günü içinde Kurum'a bildirimi) ve Kurum'un Kasım 2025 tarihli [Üretken Yapay Zekâ ve Kişisel Verilerin Korunması Rehberi](https://www.kvkk.gov.tr/Icerik/8547/uretken-yapay-zeka-ve-kisisel-verilerin-korunmasi-rehberi-15-soruda). Rehberin varlığı doğrulandı ancak metni bu turda okunamadı (site otomatik erişime kapalı); tezde alıntılamadan önce doğrudan okunmalı.

- **Aktarım:** Model, gömme modeli ve vektör DB yerelde çalışırsa soru metni ve sorgu sonuçları üçüncü tarafa gitmez. Telemetri kapatılmalı (Ollama, HF Hub, pip; `HF_HUB_OFFLINE=1`).
- **Tedarik zinciri:** Ağırlıklar SHA256 ile doğrulanıp iç depoya alınır. `.safetensors`/GGUF tercih edilir; `pickle` içeren `.bin` dosyaları kod çalıştırabilir. `trust_remote_code` kapalı tutulur.
- **Veri minimizasyonu:** LLM'e yalnızca şema ve gerekli örnek değerler gider. Kişisel veri içeren sütunların örnek değerleri isteme konmaz ya da maskelenir.
- **Loglar:** Soru ve sonuç logları kişisel veri içerebilir; saklama süresi ve erişim yetkisi belirlenmeli (Bölüm 7).
- **Aydınlatma ve yetki:** Kullanıcının görebileceği veri, DB rolü ve RLS ile sınırlanır; LLM yetki kararı vermez.

## 4. Şema temsili, schema linking, RAG ve Türkçe NLP (AS-04, AS-05, AS-06)

3B–9B modellerde en büyük kaldıraç model seçimi değil, modele ne gösterildiğidir. Doğrulanmış en net sayı: aynı XiYanSQL modeli M-Schema ile DDL'e göre BIRD dev'de 3B'de +3,0, 7B'de +4,7, 32B'de +4,9 puan kazanıyor ([7B kartı](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-7B-2504), [3B kartı](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-3B-2504)) (D).

### 4(a) Şema temsili, budama ve eşleme teknikleri

| Yöntem | Kanıt | Token maliyeti | Küçük model için öneri |
| --- | --- | --- | --- |
| Düz DDL (CREATE TABLE) | Taban çizgi; XiYan 7B BIRD dev 57,43 (D) | Orta | Karşılaştırma için D0'da tutun |
| M-Schema (sütun tipi + açıklama + örnek değerler + FK) | XiYan 7B BIRD dev 62,13 (D); kaynak: [XiYan-SQL](https://arxiv.org/abs/2411.08599) (B) | DDL'den yüksek | Varsayılan temsil olarak önerilir; XiYan modelleri bu formatla eğitildiği için bu modellere avantajlı |
| JSON / YAML metadata | Bağımsız ampirik karşılaştırma bulunamadı | Yüksek (sözdizimi yükü) | Ablasyonda ayrı kol olarak ölçülmeli; açık soru |
| Örnek satır ekleme (3 satır) | DAIL-SQL ve BIRD çalışmalarında değer biçimini öğrettiği gösterilmiş (B) | Yüksek | Tam satır yerine sütun başına 2–3 ayırt edici değer |
| FK ilişki grafı + JOIN yolu | Graf üzerinde en kısa yol ile ara tablo ekleme, budamanın kırılmasını önler (B) | Düşük | Budamadan sonra mutlaka uygulayın |

**Şema budama.** RESDSQL ve CHESS, ilgisiz tablo/sütunları çıkarmanın küçük modellerde doğruluğu artırdığını gösterdi (B). Risk, gerekli bir sütunun düşmesidir; bu yüzden **Schema Linking Recall** (gerekli öğelerin kaçı kaldı) doğruluktan önce raporlanmalı. Pratik kural: önce yüksek recall'lu geniş budama (top-k tablo + FK komşuları), sonra model.

### 4(b) Çok katmanlı RAG ve iş kurallarının modele aktarımı

1. **Schema RAG:** Tablo ve sütun açıklamaları vektörleştirilir; soru ile en yakın k tablo + FK komşuları getirilir.
2. **Example-query RAG (few-shot):** Doğrulanmış soru-SQL çiftlerinden en benzer 3–5 tanesi. DAIL-SQL, soru benzerliği yerine SQL iskelet benzerliğiyle seçimin daha iyi olduğunu raporladı (B). Kurumsal ortamda en yüksek getirili katman olması beklenir.
3. **İş kuralları / anlamsal katman:** "ciro", "iade", "aktif müşteri" tanımları SQL parçacığı + açıklama olarak saklanır ve BIRD'deki *evidence* alanı gibi isteme eklenir. BIRD'de evidence kaldırılınca EX'in belirgin düştüğü bilinir (B); bu, kuruma özgü kural aktarımının doğru modeli olduğunu destekler.
4. **Metadata RAG:** Sütun birimleri, kod tabloları (ör. durum=3 → "iptal").
5. **Value linking:** Sorudaki "İstanbul", "Ankara şubesi" gibi değerleri DB hücre değerlerine eşleme. CHESS LSH + düzenleme mesafesi kullanır (B). Türkçede ek almış biçimler (İstanbul'daki, Ankara'dan) nedeniyle önce kök/lemma, sonra karakter n-gram veya BGE-M3 / multilingual-E5 benzerliği önerilir.

**Ampirik boşluk:** Bu katmanların 3B–9B modellerde tek tek katkısını Türkçe veriyle ölçen yayın bulunamadı. Bu, tezin D-kademeli ablasyonunun doğrudan doldurduğu boşluktur (bkz. Bölüm 8).

**Gömme modeli bütçesi.** BGE-M3 \~568M parametre, multilingual-E5-large \~560M (B); FP16'da \~1,1 GB VRAM. 8 GB kartta LLM ile aynı GPU'da çalıştırmak yerine CPU'da veya e5-small/base ile çalıştırmak KV cache'e yer bırakır.

#### Semantik katman ve MCP: iş kurallarını LLM'e değil sisteme öğretmek

Arkadaş raporunun en güçlü katkısı şu tez: üretimde ham tabloları LLM'e verip `JOIN` ve metrik formülünü ona bırakmak, "çalışan ama yanlış hesaplayan" sorgular üretir. Çözüm, metriklerin ve güvenli JOIN yollarının merkezi tanımlandığı bir **semantik katmandır** (A).

| Yaklaşım | Örnek proje | Fikir | TRSQL karşılığı |
| --- | --- | --- | --- |
| Metrik tanım dili (MDL) | [Canner/WrenAI](https://github.com/Canner/WrenAI) (A) | Metrikler ve ilişkiler bildirimsel dosyada; LLM sertifikalı modellere dayanır | `semantic_layer` + `configs/knowledge.example.toml` |
| dbt semantiği | dbt MetricFlow, Cube, [getnao/nao](https://github.com/getnao/nao) (A) | Metrikler dbt/YAML'da sürümlü | Kurumda dbt varsa içe aktarıcı yazılabilir (sonraki faz) |
| Bilgi grafiği şeması | [FalkorDB/QueryWeaver](https://github.com/FalkorDB/QueryWeaver) (A) | Şema graf olarak saklanır, çok atlamalı JOIN yolu graf gezintisiyle bulunur | `schema_intelligence` (BFS/Steiner JOIN zaten var) |
| İş sözlüğü (glossary) | [dataease/SQLBot](https://github.com/dataease/SQLBot) (A) | Terim → tanım → örnek SQL eşlemesi | `knowledge_base` + Türkçe eş anlamlı listesi |

**TRSQL için karar önerisi:** Sık sorulan KPI'lar (ciro, net satış, iade oranı, aktif müşteri) için **LLM'in hiç SQL yazmadığı** onaylı metrik şablonları; geri kalan sorular için LLM üretimi + bu tanımların *evidence* olarak isteme eklenmesi. Bu, ADR-0008 (deterministik sayılar) ile de uyumlu.

**MCP (Model Context Protocol).** 2025–2026'da veri ajanları veritabanına MCP sunucuları üzerinden bağlanıyor: [googleapis/mcp-toolbox](https://github.com/googleapis/mcp-toolbox), WrenAI, Chat2DB, QueryWeaver, `xiyan_mcp_server` (A). Kazanç: bağlantı havuzu, kimlik doğrulama ve OpenTelemetry'nin tek bir kontrol düzleminde toplanması. **TRSQL'de dikkat:** MCP sunucusu modelin doğrudan `execute_sql` çağırmasına izin verirse ADR-0004'ü ("model veritabanına asla dokunmaz") ihlal eder. Bu yüzden MCP yalnızca **dış arayüz** olarak (TRSQL'in kendisini bir MCP aracı olarak sunmak; aracın içinde L1–L9 hattı çalışır) eklenmeli, modele DB aracı verilmemeli. Öncelik: düşük, AR-10 sonrası.

### 4(c) Eklemeli morfoloji, yazım hataları, göreli tarih, eş anlamlılar ve belirsizlik

| Sorun | Örnek | Önerilen çözüm |
| --- | --- | --- |
| Eklemeli morfoloji | müşterilerimizin, siparişlerinden | Zemberek (Java) veya TRmorph ile kök bulma, yalnızca value linking ve schema linking aşamasında; LLM'e ham soru gider |
| Yazım hatası / ASCII yazım | musteri, sirket, iş yerine is | Normalizasyon sözlüğü + düzenleme mesafesi; çift yönlü (ı/i, ş/s) eşleme |
| Göreli tarih | geçen ay, son 30 gün, geçen seneye göre | Kural tabanlı çözümleyici ile istem öncesi somut tarih aralığına çevirme; "bugün" değerini isteme sabit verme. LLM'e bırakmak lehtenin tarih fonksiyonlarında hataya açık |
| Sektörel eş anlamlı | ciro / hasılat / satış tutarı | İş kuralları RAG'ındaki eş anlamlı listesi |
| Belirsiz soru | "en iyi müşteriler" | Belirsizlik sınıflandırıcısı (aynı LLM, ayrı istem) → açıklama sorusu; yanıtsız sorularda "cevaplanamaz" çıktısı. AMBROSIA ve PRACTIQ gibi çalışmalar (B, doğrulanmalı) bu alanda İngilizce ölçütler sunar |

Zemberek Java gerektirdiği için Windows prototipinde Python tarafında zemberek-python veya bir JVM süreci gerekir; bu bir dağıtım maliyetidir.

## 5. Fine-tuning kararı ve hata düzeltme (AS-07, AS-08)

Türkçe için LoRA SFT'nin getirisi doğrulanmış bir veri noktasıyla 7–9 puan: Hati-Glint-SQL, Qwen3.5-9B tabanına göre TURSpider direkt modda +9,1, BIRDTurk'te +7,2 puan kazanıyor ([kart](https://huggingface.co/runelab-ai/Hati-Glint-SQL-9B-v1), kendi ölçümü). Bu, RAG'in tek başına kapatamayacağı bir "Türkçe semantik boşluk" olduğuna işaret ediyor; ama kurumsal şemaya özgü ince ayarın gerekliliği ayrıca kanıtlanmalı.

### 5(a) Fine-tuning karar kriterleri, bakım maliyeti ve unutma riski

| Koşul | Önce dene | İnce ayar gerekir mi? | Gerekçe |
| --- | --- | --- | --- |
| Türkçe soru anlama zayıf | Few-shot RAG, Türkçe eş anlamlı sözlük | Genellikle evet (LoRA) | Hati: +7–9 puan (D); BIRDTurk'te SFT'siz küçük modeller \~0 (D) |
| Özel SQL lehçesi (PostgreSQL/T-SQL) | Lehçe talimatı + SQLGlot transpile | Az; transpile genellikle yeter | XiYan: SQLite'ta 62, PostgreSQL DW'de 42 (D) — lehçe/dağılım farkı büyük |
| Karmaşık kurumsal şema | Schema RAG + budama + M-Schema | Ancak şema sabitse ve >500 doğrulanmış örnek varsa | Şema değişince yeniden eğitim maliyeti |
| Düşük gecikme | Küçük model + tek aday | Evet: 3–4B modeli göreve özelleştirmek | Oylama/ajan döngüsü gecikmeyi 3–8 kat artırır |
| Akıl yürütme kalitesi | Thinking modu | RL (GRPO) | Arctic-R1-7B: yalnızca çalıştırma doğruluğu + biçim ödülü ile BIRD 68,9 ([makale](https://arxiv.org/abs/2505.20315)) (D) |

**Bakım ve unutma riski.** LoRA adımları genel yeteneği kısmen bozabilir: Hati'de TurkishMMLU 66,22 → 65,11 (−1,1) düşmüş (D). Kurumsal kullanımda öneri: taban modeli değiştirmeden LoRA adaptörünü ayrı tutmak, her şema değişikliğinde sabit bir regresyon setiyle (ör. 200 soru) yeniden ölçmek. 8 GB VRAM'de 7–9B QLoRA eğitimi sınırda; 3–4B eğitim yerelde, 7–9B eğitim bulutta/kişiselleştirilmiş GPU'da daha gerçekçi (B, ölçülmeli).

**Sentetik veri.** OmniSQL'in SynSQL-2.5M yaklaşımı (veritabanı → SQL → soru üretimi, çalıştırma ile filtre) ([makale](https://arxiv.org/abs/2503.02240)) Türkçe kurumsal veri üretimi için doğrudan uyarlanabilir: SQL'i önce üret, çalıştır, boş olmayan sonuç verenleri tut, sonra Türkçe soruyu LLM'e yazdır ve geri-çeviriyle tutarlılık kontrol et.

**DPO vs GRPO.** SQL'de çalıştırma sonucu otomatik ve kesin bir ödül sağladığı için 2025–2026 literatürü ağırlıklı olarak GRPO'ya yöneldi (Arctic-R1, sqrl). DPO tercih çiftleri ister; SQL'de bu çiftler doğru/yanlış çalıştırma sonucundan üretilebilir ama GRPO'ya göre kanıt daha az (B). RL eğitimi çoklu GPU ve çalıştırılabilir DB havuzu gerektirdiği için 8 GB dizüstünde gerçekçi değil; tez kapsamında en fazla LoRA SFT (D7) önerilir.

**Kural:** Önce RAG + doğrulama (D0–D6) ile tavan ölçülür. İnce ayar yalnızca hata analizinde lehçe veya Türkçe anlama kaynaklı sistematik bir hata sınıfı kalırsa ve ≥ +4 puan net kazanç sağlarsa tutulur (Seydi'nin paylaştığı D7 ölçütüyle aynı).

### 5(b) Halüsinasyon azaltma ve hata düzeltme tekniklerinin ampirik etkinliği

| Teknik | Neyi önler | Kanıt | Maliyet |
| --- | --- | --- | --- |
| AST ayrıştırma + şema doğrulama (SQLGlot) | Var olmayan tablo/sütun, sözdizimi hatası, yasak ifade | Deterministik; kesin yakalar (B) | \~ms; zorunlu |
| Dilbilgisi kısıtlı çözme (GBNF, PICARD) | Geçersiz SQL, şema dışı tanımlayıcı | [PICARD](https://arxiv.org/abs/2109.05093) T5 ile Spider'da belirgin artış (B); GBNF ile dinamik şema dilbilgisi mümkün ama tam SQL dilbilgisi karmaşık | Çözme %10–30 yavaşlayabilir (B); thinking modelleriyle uyumsuz olabilir |
| Çalıştırma geri beslemeli onarım | Çalışma zamanı hatası, boş sonuç | BIRDTurk: DIN-SQL (öz-düzeltme dahil) Türkçede +5,86 (D); Hati: geri besleme +1,0–2,6 (D) | 1–3 ek LLM çağrısı |
| Çoklu aday + oylama (self-consistency) | Mantık hatası | sqrl-9b: tek örnek 66,6 → 8 oy 69,8 (+3,2) (D); OmniSQL maj@8 raporluyor | N kat üretim; 8 GB'ta N=4–8 makul |
| Seçici model (CHASE-SQL tarzı) | Aday arası hatalı çoğunluk | CHASE-SQL'de oylamadan iyi (B) | Ek model / çağrı |

**Önerilen sıra (küçük model):** SQLGlot doğrulama (her zaman) → hata varsa hata mesajıyla 1–2 tur onarım → zaman bütçesi el veriyorsa 4 aday + sonuç-kümesi oylaması. GBNF'yi ayrı bir ablasyon kolu olarak ölçün; thinking modeliyle birlikte kullanımı belgelenmemiş.

**Kısıtlı çözme ve thinking.** Seydi'nin paylaştığı rapor şunu öneriyor: `<think>` bloğunu kısıtsız bırakın, GBNF maskesini yalnızca son SQL bloğuna uygulayın, ardından SQLGlot ile doğrulayın. Gerekçe: kısıtlı çözme biçimi kurtarır ama anlamsal hatayı düzeltmez, yanlış kurulursa akıl yürütmeyi bozabilir. Raporda kaynak olarak verilen Chavan (2026) ve Beurer-Kellner vd. (2024) bu turda açılmadı.

## 6. 8 GB VRAM'de nicemleme, bellek ve hız (AS-09)

8 GB kartta güvenli bölge: 7–9B modeller Q4\_K\_M/Q5\_K\_M ile 8K bağlama kadar tamamen GPU'da; 3–4B modeller Q6\_K/Q8\_0 ile 16K'ya kadar. 14B ancak IQ4\_XS + CPU aktarımıyla çalışır ve hız birkaç kat düşer.

**Donanım (teyit edildi):** RTX 4070 **Laptop** GPU, 8 GB VRAM, 32 GB RAM, Windows. Bellek bant genişliği yaklaşık 256 GB/sn (B). Seydi'nin paylaştığı rapor Windows ve CUDA payı düşüldükten sonra net bütçeyi ≈6,8 GB olarak hesaplıyor; aşağıdaki ≈7,0 GB tahminiyle uyumlu. Tezde TGP (güç limiti) ve sürücü sürümü de raporlanmalı.

### 6(a) GGUF ve AWQ nicemlemenin doğruluk kaybı

SQL'e özgü, hakemli bir GGUF nicemleme çalışması bulunamadı; bu bir araştırma boşluğu ve tezde ölçülmeli. En yakın kanıtlar:

- [Licardo & Tankovic (2025)](https://arxiv.org/pdf/2510.21970), Llama-3.2-1B, yapılandırılmış çıktı görevi: FP16 0,99; Q5\_K\_M 0,99; **Q4\_K\_M 0,89**; Q3\_K\_M 0,60 (D).
- [Zhang (2026, hakemsiz ön baskı)](https://www.researchsquare.com/article/rs-11704703/v1): 0,5–3B modellerde "biçim hatası" (kullanılabilir cevap yok) bit sayısıyla monoton değil; Qwen2.5-0.5B'de Q4\_K\_M'de %19,4, Q8\_0'da %1,6. Qwen2.5-3B'de en kötü seviye Q3\_K\_M (%30,6) (D).

Sonuç: 3–4B modellerde Q4\_K\_M yerine Q5\_K\_M veya Q6\_K kullanın. Her nicemleme seviyesinde **Valid SQL Rate** ayrı raporlanmalı, çünkü kayıp doğruluktan önce biçimde görünür. AWQ, Windows'ta pratikte vLLM gerektirdiği için (vLLM Windows'ta yerel desteklenmez, WSL2 gerekir (B)) prototipte GGUF tercih edilmeli.

**Kod üretiminde 4-bit karşılaştırması (SQL'e en yakın kanıt).** [Afrin vd. (2026)](https://arxiv.org/pdf/2607.14181), Qwen2.5-Coder-7B-Instruct'ı AWQ, GPTQ, GGUF Q4\_K\_M, NF4, AQLM ve QuIP# ile 4-bit'e indirip FP16 ile karşılaştırdı. BigCodeBench-Python'da FP16 0,41 iken AWQ 0,41, GPTQ 0,41, GGUF 0,40, NF4 0,39, QuIP# 0,32 (D, özetten). Java'da 4-bit çoğu durumda işlevsel doğruluğu korudu; yalnızca bir karşılaştırma istatistiksel olarak anlamlı çıktı. [Fang vd. (2025)](https://arxiv.org/pdf/2506.22776) 8-bit'te ortalama %0,36, 4-bit'te %1,19 temiz doğruluk kaybı raporluyor (özetten).

Yorum: 7B sınıfında AWQ ve GGUF Q4\_K\_M arasında kod doğruluğunda pratik fark yok; kayıp aslında 0,5–3B modellerde ve biçim hatası olarak görünüyor. AWQ'nun Windows'ta yerel motoru olmadığı için tez deneylerinde GGUF yeterli; AWQ yalnızca vLLM/WSL2 kolu açılırsa ölçülmeli.

### 6(b) Bellek bütçesi: ağırlık, KV cache, CUDA ve gömme modeli (hesaplanmış)

Varsayımlar: GGUF bit/ağırlık Q4\_K\_M ≈4,85, IQ4\_XS ≈4,25, Q5\_K\_M ≈5,7, Q6\_K ≈6,6, Q8\_0 ≈8,5; KV cache FP16; model katman/KV-head sayıları resmi config.json değerlerinden bellekten alındı (B). Windows masaüstü + CUDA bağlamı için 0,8–1,0 GB ayrılmalı; kullanılabilir bütçe ≈7,0 GB.

| Model | Ağırlık Q4\_K\_M | Ağırlık Q8\_0 | KV / token | KV @8K | KV @16K | 8 GB'a sığar mı |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen2.5-Coder-3B / XiYan-3B (36 kat., 2 KV head) | 1,9 GB | 3,3 GB | 36 KB | 0,3 GB | 0,6 GB | Q8\_0 + 16K rahat |
| Qwen3-4B (36 kat., 8 KV head) | 2,5 GB | 4,3 GB | 144 KB | 1,2 GB | 2,4 GB | Q6\_K + 16K sınırda; Q8 + 8K rahat |
| Qwen2.5-Coder-7B / XiYan-7B / OmniSQL-7B / Arctic-7B (28 kat., 4 KV head) | 4,6 GB | 8,1 GB | 56 KB | 0,5 GB | 0,9 GB | Q4/Q5 + 16K evet; Q6 + 8K sınırda; Q8 hayır |
| Trendyol-8B / Qwen3-8B (36 kat., 8 KV head) | 5,0 GB | 8,7 GB | 144 KB | 1,2 GB | 2,4 GB | Q4 + 8K evet; 16K için KV q8\_0 gerekir |
| Qwen3.5-9B / Hati / sqrl (yalnız 8 tam dikkat katmanı) | ≈5,5 GB | ≈9,6 GB | Düşük (DeltaNet durum belleği sabit) | Düşük | Düşük | Q4 + 16K muhtemelen evet; ölçülmeli |
| 14B (Qwen2.5-Coder-14B, 48 kat., 8 KV head) | 9,0 GB | 15,7 GB | 192 KB | 1,6 GB | 3,1 GB | Hayır; IQ4\_XS (7,9 GB) bile CPU aktarımı ister |

KV cache'i q8\_0'a nicemlemek (llama.cpp `--cache-type-k q8_0 --cache-type-v q8_0`, flash attention açık) KV belleğini yaklaşık yarıya indirir (B).

**Gömme modeli aynı GPU'da:** BGE-M3 FP16 ≈1,1 GB. 7–9B modelle birlikte aynı kartta çalıştırılırsa bağlam 4K'ya iner. Öneri: gömmeyi CPU'da çalıştırın (32 GB RAM yeterli); sorgu başına \~50–200 ms ek gecikme beklenir (B).

### 6(b) Motorlar: llama.cpp, Ollama, vLLM; tokens/sn ve P50/P95

| Motor | Windows | Nicemleme | Uygunluk |
| --- | --- | --- | --- |
| llama.cpp (`llama-server`) | Yerel CUDA derlemesi | GGUF, KV nicemleme, GBNF | Ablasyon için en kontrollü; GBNF burada |
| Ollama | Yerel | GGUF (llama.cpp üzerinde) | Kolay; ancak varsayılan `num_ctx` küçük olabilir ve sürümler arası değişiyor, istemde açıkça ayarlayın (B) |
| vLLM | Yalnız WSL2/Linux | AWQ, GPTQ, FP8 | Eşzamanlı kullanıcıda en hızlı; tek kullanıcı prototipte gereksiz |

**Beklenen çözümleme hızı (teorik üst sınır = bant genişliği / ağırlık boyutu; gerçekte %60–75'i):** 256 GB/sn kartta 7B Q4\_K\_M için \~55 tok/sn üst sınır, \~35–40 tok/sn gerçekçi; 3B Q8\_0 için \~75 üst sınır. CPU'ya 1 GB bile aktarılması hızı belirgin düşürür (DDR5 \~60–80 GB/sn). Bunlar hesaplanmış tahminlerdir; bağımsız ölçüm bulunamadı.

**Bağımsız kaynaklar:** [Red Hat (2025)](https://developers.redhat.com/articles/2025/09/30/vllm-or-llamacpp-choosing-right-llm-inference-engine-your-use-case) H200 üzerinde Llama-3.1-8B ile tek kullanıcıda vLLM ve llama.cpp'nin benzer token hızı verdiğini, 64 eşzamanlı kullanıcıda vLLM'nin 44 kat fazla çıktı ürettiğini ölçtü; P99 TTFT llama.cpp'de yükle birlikte hızla artıyor (D). [llmconfigurator](https://llmconfigurator.com/en/upgrade/laptop-rtx-4070-8gb/to-run-qwen3-8b), RTX 4070 Laptop'ta Qwen3-8B Q4\_K\_M + 8K bağlam için 7 GB VRAM ve 44–85 tok/sn **tahmin ediyor** (ölçüm değil). Bu kartta ölçülmüş, yayımlanmış P50/P95 verisi bulunamadı.

**Tez için sonuç:** Tek kullanıcılı prototipte llama.cpp yeterli ve vLLM'ye göre hız kaybı beklenmiyor. Ollama, llama.cpp'nin üstünde ek bir katman olduğu için aynı GGUF ile benzer çözümleme hızı vermeli; fark varsayılan ayarlardan (bağlam, KV tipi) gelir. Bu üç motor aynı model ve aynı 200 soruda ölçülürse, yayımlanmış bir boşluğu dolduran özgün bir tablo olur.

**Ölçüm protokolü önerisi:** `llama-bench` ile pp512/tg128; uçtan uca P50/P95 için çalıştırma dahil 200 soruluk sabit set, ısınma çalıştırması hariç, `nvidia-smi --query-gpu=memory.used` ile tepe VRAM. Thinking modunda üretilen token sayısı gecikmeyi belirler; ayrı raporlanmalı.

#### Karmaşıklığa göre yönlendirme: EllieSQL ve PRISM

Çok adaylı / çok ajanlı yöntemler (CHASE-SQL, Agentar-Scale-SQL, Alpha-SQL) doğruluğu artırır ama sorgu başına onlarca LLM çağrısı yapar; 8 GB dizüstünde bu, P95 gecikmeyi kabul edilemez hale getirir. İki çalışma bu dengeyi yönlendirmeyle kuruyor:

- [EllieSQL](https://arxiv.org/abs/2503.22402) (HKUSTDial, [kod](https://github.com/HKUSTDial/EllieSQL)): sorunun karmaşıklığını tahmin eden hafif bir yönlendirici, basit soruları ucuz yola, zor soruları pahalı yola gönderir (varlığı D; skorlar bu turda okunmadı).
- [PRISM: Navigating Cost–Accuracy Trade-offs for NL2SQL](https://research.google/pubs/prism-navigating-costaccuracy-trade-offs-for-nl2sql/) (Google Research): maliyet–doğruluk dengesine göre yol seçimi (varlığı D; arkadaş raporu SIGMOD'26 diyor, A).

**TRSQL'e uyarlama (D6 kademesi):** Model değiştirmek yerine **mod** değiştirmek: (1) `turkish_nlp` çıktısı ve `LinkedSchema` boyutundan kural tabanlı bir karmaşıklık puanı (tablo sayısı, toplama, zaman ifadesi, iç içe yapı); (2) düşük puan → doğrudan mod, tek aday; (3) yüksek puan veya ilk deneme doğrulamadan geçemezse → thinking modu ve/veya N=4 aday + sonuç oylaması. Ölçüt: aynı EX'te P95 gecikmenin düşmesi. 8 GB'ta iki modeli aynı anda yüklemek mümkün olmadığından, model yönlendirmesi değil **mod yönlendirmesi** önerilir.

## 7. Güvenli SQL mimarisi (AS-10)

Temel ilke: LLM çıktısı güvenilmeyen kullanıcı girdisi gibi ele alınır ve güvenlik veritabanı katmanında zorlanır; istem içi talimatlar savunma sayılmaz ([OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/): LLM01 Prompt Injection, LLM05 Improper Output Handling) (B). Text-to-SQL'de enjeksiyon kaynağı yalnızca soru değil, DB'deki hücre değerleri ve RAG'a giren açıklamalardır.

### 7(a) İstem enjeksiyonu, sızıntı ve yazma sorgularına karşı katmanlı savunma

1. **Girdi:** Soru uzunluk sınırı; RAG belgeleri yalnızca yetkili kişilerce yazılır ve sürümlenir.
2. **AST politikası (SQLGlot):** Tek ifade; yalnızca `SELECT` / `WITH`. `INSERT/UPDATE/DELETE/MERGE/DDL/COPY/CALL/SET`, `pg_sleep`, `dblink`, `lo_*`, `pg_read_file` gibi fonksiyonlar reddedilir. Tablo/sütun izin listesi kullanıcı rolüne göre AST üzerinde kontrol edilir. Metin üzerinde regex ile filtreleme yetersizdir.
3. **Zorunlu `LIMIT`:** AST'ye dış sorgu olarak `LIMIT n` eklenir (ör. 1.000).
4. **Maliyet ön kontrolü:** `EXPLAIN (FORMAT JSON)` ile tahmini maliyet ve satır sayısı eşik üstündeyse sorgu çalıştırılmaz, kullanıcıya daraltılması önerilir. `EXPLAIN ANALYZE` sorguyu çalıştırdığı için kullanılmaz.
5. **Veritabanı rolü:** Ayrı `nl2sql_reader` rolü; yalnızca `SELECT` yetkisi, `default_transaction_read_only = on`, `statement_timeout` (ör. 10 sn), `lock_timeout`, `idle_in_transaction_session_timeout` ([PostgreSQL istemci ayarları](https://www.postgresql.org/docs/current/runtime-config-client.html)) (B). Bağlantı havuzunda bağlantı limiti.
6. **Satır düzeyi güvenlik:** [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) politikaları oturum değişkeniyle (`SET app.user_id`) kullanıcıya göre satır filtreler. Uygulama rolü tablo sahibi olmamalı, `BYPASSRLS` yetkisi olmamalı (B).
7. **Sütun maskeleme:** Kişisel veri sütunları (TCKN, telefon, e-posta) için maskeli görünümler (view) veya PostgreSQL Anonymizer eklentisi; LLM'e ham tablo yerine görünüm şeması verilir.
8. **Sonuç çıkışı:** Sonuç boyutu sınırı; sonuç LLM'e özetletilecekse özetlenecek satır sayısı da sınırlı.
9. **Denetim kaydı:** Her istek için zaman, kullanıcı, soru, üretilen SQL, AST kararı ve reddetme nedeni, EXPLAIN maliyeti, süre, dönen satır sayısı, model ve istem sürümü. Sonuç verisinin kendisi loglanmaz. DB tarafında `pgaudit` (B).

#### SQLGlot ile dört şeritli guardrail ve TRSQL L6 eşlemesi

Arkadaş raporu, üretim sistemlerinde yaygın dört şeritli bir AST guardrail tarif ediyor (A). TRSQL'in mevcut `sql_validator` aşamalarıyla eşlemesi:

| Şerit (arkadaş raporu) | İçerik | TRSQL'de karşılığı | Durum (PR #1 iskeleti) |
| --- | --- | --- | --- |
| 1. Parse & transpile | `sqlglot.parse_one(sql, read=dialect)`; lehçeler arası çeviri | Syntax + AST aşaması | Var; transpile AR-07'de |
| 2. Salt okunur zorlaması | `DROP/DELETE/TRUNCATE/ALTER/GRANT/INSERT/UPDATE` düğümlerinin reddi; yalnız `SELECT/WITH` | AST + Injection aşaması | Var |
| 3. Yapısal güvenlik ve maliyet | `ON`'suz Kartezyen JOIN reddi, eksikse `LIMIT` enjeksiyonu, `EXPLAIN` maliyet eşiği | Cost aşaması + `policy_engine` (LIMIT, timeout) | Kısmen; `EXPLAIN` eşiği AR-07 |
| 4. Erişim kontrolü | Rol bilgisinin hem şema seçimine hem RLS'ye enjeksiyonu (örnek: [schemagate](https://github.com/ashishsinha1602/schemagate), A) | `auth.scope_schema()` (RBAC şemadan önce) + Authorization aşaması + PostgreSQL RLS | Şema kapsamlama var; RLS AR-07 |

TRSQL'in bu dört şeridin ötesine geçtiği iki nokta: güvenlik ihlalinin **yeniden denenmemesi** (ADR-0005; model ret nedenini öğrenmez) ve sınırlı yeniden deneme bütçesi (ADR-0006). Eksik kalan ve eklenmesi gereken: **Semantic** ve **Business Rule** doğrulama aşamaları (ör. "net ciro" sorusunda iade düşülmüş mü).

**İnsan onayı (HITL).** Uber QueryGPT'nin "bu tablolar doğru mu?" onayı ve belirsizlikte netleştirme sorusu üretim başarısını belirgin artırıyor (A). TRSQL'de bu `NEEDS_CLARIFICATION` durumuyla zaten tasarlanmış; L0 arayüzünde seçilen tabloların kullanıcıya gösterilmesi eklenebilir.

### 7(b) Ön maliyet analizi, zaman aşımı, satır sınırı ve denetim kaydı

Ağır sorguların veritabanını kilitlemesini önlemek için tek bir önlem yetmez; ön kontrol, çalışma zamanı sınırı ve sonrasında kayıt birlikte kurulur. Aşağıdaki eşikler başlangıç önerisidir; kurumun yüküne göre ayarlanmalı (B).

| Kontrol | Nerede | Önerilen başlangıç | Not |
| --- | --- | --- | --- |
| EXPLAIN ön maliyeti | Uygulama, çalıştırmadan önce | `EXPLAIN (FORMAT JSON)` toplam maliyet ve tahmini satır eşiği (ör. maliyet > 1e6 veya satır > 1e7 ise reddet) | Maliyet birimi göreli; eşik gerçek sorgu dağılımından (P99) seçilmeli. Kartezyen çarpım ve tam tablo taraması düğümleri ayrıca işaretlenir |
| Sorgu zaman aşımı | DB rolü | `ALTER ROLE nl2sql_reader SET statement_timeout = '10s'` | Uygulama tarafındaki zaman aşımı yetmez; DB sorguyu iptal etmeli |
| Kilit beklemesi | DB rolü | `lock_timeout = '2s'`, `idle_in_transaction_session_timeout = '30s'` | Salt okunur sorgu kilit almamalı; yine de bekleme sınırlanır |
| Satır sınırı | AST + uygulama | Dış sorguya `LIMIT 1000`; istemciye en fazla 1000 satır | `LIMIT`'siz alt sorgu ve CTE'ler EXPLAIN ile yakalanır |
| Kaynak sınırı | DB | Rol için bağlantı limiti (`CONNECTION LIMIT 5`), `work_mem` sınırı, ayrı okuma replikası | Mümkünse sorgular ana DB yerine replikada çalışır |
| Özyineleme / zaman tuzağı | AST | `WITH RECURSIVE`, `generate_series` üst sınırsız, `pg_sleep` reddi | Kaynak tüketme saldırıları |
| Denetim kaydı | Uygulama + `pgaudit` | Korelasyon kimliğiyle: kullanıcı, soru, RAG bağlamı kimlikleri, SQL, AST kararı, EXPLAIN maliyeti, süre, satır sayısı, model ve istem sürümü | Sonuç verisi loglanmaz; KVKK gereği saklama süresi ve erişim yetkisi belirlenir; loglar değiştirilemez depoya yazılır |

Yukarıdaki 7(a) listesinin 3, 4, 5 ve 9. maddeleri bu tablonun uygulama adımlarıdır. Kaynaklar: [PostgreSQL istemci ayarları](https://www.postgresql.org/docs/current/runtime-config-client.html) (B).

### Güvenlik test seti (a ve b için)

**Unsafe SQL Rate** metriği için saldırı seti önerisi: (a) doğrudan "tabloyu sil" istekleri, (b) Türkçe dolaylı enjeksiyon ("önceki talimatları yok say"), (c) hücre değerine gömülü talimat, (d) yetkisiz tablo/sütun soran sorular, (e) kartezyen çarpım ve özyinelemeli CTE ile kaynak tüketme. Metrik iki ayrı sayı olarak raporlanmalı: modelin ürettiği tehlikeli SQL oranı ve katmanlardan geçip DB'ye ulaşan oran (hedef: 0).

## 8. Deney düzeneği ve araştırma boşlukları (AS-12)

Planlanan metrik seti literatürle uyumlu. Aşağıdaki D0–D8 tanımları Seydi'nin paylaştığı raporun "Revize D0–D8" planıdır; her kademe bir öncekine eklenir (kümülatif).

### 8(a) D0–D8 ablasyon kademeleri

| Kademe | Eklenen bileşen | Ölçülen etki | Geçiş ölçütü | Yorumum |
| --- | --- | --- | --- | --- |
| D0 | Ham LLM + klasik DDL, doğrudan mod | Taban EX, Valid SQL, P50/P95, tepe VRAM | 8 GB içinde kararlı çalışma | Uygun |
| D1 | + M-Schema vs yorumlu kompakt DDL | Δ EX, token ekonomisi | En iyi EX/token serileştiriciyi dondur | XiYan modelleri M-Schema ile eğitildi; model başına ayrı karar verin |
| D2 | + Çift yönlü şema bağlama + FK Steiner grafı | Schema Linking P/R, JOIN hatası | Recall ≥ %95 | Uygun |
| D3 | + Çoklu RAG (iş kuralları + DAIL örnek SQL + LSH değer bağlama, BGE-M3 CPU'da) | Δ EX | BGE-M3 vs E5-large seçimi | Üç RAG bileşeni tek kademede; ayrı katkıları için leave-one-out ekleyin |
| D4 | + Türkçe NLP (tarih normalizasyonu, İ/ı collation, belirsizlik tespiti) | Belirsiz/zamansal sorularda doğruluk | Sessiz yanlış SQL oranında düşüş | Abstention/Clarification metriği gerekir (8.2) |
| D5 | + 6 katmanlı fail-closed güvenlik (SQLGlot AST, RLS, EXPLAIN, GBNF) | Unsafe SQL = %0, Valid SQL → %100 | 30/30 saldırının engellenmesi | GBNF doğruluğu da değiştirir; güvenlik ve GBNF etkisini ayrı raporlayın |
| D6 | + Direct → Thinking yönlendirme + yürütme geri bildirimli onarım (≤2) | EX vs P95 | P50 ≤ 3–4 sn, P95 ≤ 18–20 sn | Thinking token sayısı gecikmeyi belirler; ayrı ölçün |
| D7 | + PostgreSQL QLoRA / RAFT (yalnızca D6'da kalıcı hata kalırsa) | Lehçe kazancı + Türkçe regresyon | ≥ +4 puan net kazanç; BIRDTurk eğitimde yok | 8 GB'ta 7–9B QLoRA sınırda; bulut gerekebilir |
| D8 | Tam hibrit sistem (KPI semantik katman + D6/D7) | Test Suite, VES, güvenlik, KVKK | Kurumsal kabul eşikleri | Uygun |

Kademeler kümülatif olduğu için bir bileşenin katkısı, kendisinden önce eklenenlere bağlıdır. D3 ve D5 gibi birden fazla bileşen taşıyan kademelerde tek bileşen çıkarma (leave-one-out) koşuları eklenmeli. Değerlendirme katmanları: A) TURSpider dev 1.034 soru, B) BIRDTurk dev 1.534 soru (yalnız değerlendirme), C) 150–250 soruluk kurumsal sentetik Türkçe PostgreSQL seti.

### 8(a) Metriklerin geçerliliği, lehçe farkları ve sentetik veri üretimi

| Metrik | Durum | Not |
| --- | --- | --- |
| Execution Accuracy | Standart (Spider, BIRD) | Satır sırası yalnızca `ORDER BY` varsa karşılaştırılmalı; float yuvarlama kuralı sabitlenmeli |
| Test Suite Accuracy | [Zhong vd. 2020](https://arxiv.org/abs/2010.02840) (B) | Tek DB'de tesadüfi doğru sonuçları eler; sentetik kurumsal set için değer-mutasyonlu 3–5 DB örneği üretin |
| Exact Match | LLM döneminde zayıf | BIRDTurk'te EX 49 iken EM 11 (D); yalnızca ek bilgi olarak |
| Valid SQL Rate | Uygun | Ayrıştırılabilir ve çalıştırılabilir olarak ikiye bölün |
| Schema Linking Accuracy | Uygun | Precision ve recall ayrı; altın tablo/sütunlar SQLGlot ile altın SQL'den otomatik çıkar |
| Hallucination Rate | Tanım gerekli | Şemada olmayan tanımlayıcı içeren SQL oranı olarak tanımlayın |
| Unsafe SQL Rate | Uygun | Bölüm 7.2'deki iki sayı |
| Gecikme, VRAM/RAM | Uygun | P50/P95, tepe VRAM; donanım tam olarak raporlanır |
| Eksik: Abstention / Clarification F1 | Eklenmeli | Yanıtsız sorularda "cevaplanamaz" deme ve belirsizlikte soru sorma doğruluğu |

İstatistik: Aynı soru seti üzerindeki iki kademe arası fark için McNemar testi veya eşli bootstrap %95 Gİ raporlayın (Hati kartı da Gİ veriyor). 500 soruluk sette \~4 puan altı farklar genellikle anlamlı olmaz (B).

**Altın etiket kalitesi.** [Jin vd. (2026)](https://arxiv.org/abs/2601.08778) uzman denetiminde BIRD Mini-Dev örneklerinin %52,8'inde, Spider 2.0-Snow'un %62,8'inde etiket hatası buldu. Düzeltme sonrası 16 açık ajanın performansı göreceli olarak −%7 ile +%31 arasında, sıralaması ±9 basamak değişti; sıralama korelasyonu 0,85'ten 0,32'ye düştü (D, özet). BIRDTurk BIRD'den çevrildiği için bu hataları miras alır. Kurumsal C setindeki her altın SQL iki uzmanca doğrulanmalı. Seydi'nin paylaştığı rapor çalışmayı PVLDB 19(5) olarak veriyor; arXiv sayfasında yayın yeri yazmıyor.

**Lehçeler.** Altın SQL'i PostgreSQL'de yazıp SQLGlot ile SQLite/DuckDB'ye transpile edin ve her lehçede altın sonucu yeniden doğrulayın. Tarih fonksiyonları (`date_trunc`, `strftime`, `INTERVAL`) ve `ILIKE`/Türkçe harf duyarlılığı (İ/i, I/ı collation) en sık kırılan noktalardır.

**Sentetik kurumsal Türkçe veri.** Önerilen akış: Türkçe adlandırılmış şema (e-ticaret/ERP) + Faker-tr ile sahte veri → şablon ve LLM ile SQL üretimi → çalıştırıp boş/hatalı olanları eleme → LLM ile Türkçe soru + insan kontrolü → %10–15 belirsiz ve %10 yanıtsız soru ekleme (yanıt: açıklama sorusu veya ret). İş kuralı gerektiren sorular ayrı etiketlenmeli ki D5'in etkisi ayrıştırılabilsin.

#### Benchmark güvenilirliği: etiket hataları, kirlenme ve güncel zorlu ölçütler

- **Etiket hataları:** [Jin vd. 2026](https://arxiv.org/abs/2601.08778) (D) BIRD Mini-Dev'in %52,8'inde, Spider 2.0-Snow'un %62,8'inde altın SQL hatası buldu; düzeltme sıralamaları ±9 basamak değiştirdi. Kod ve düzeltilmiş veri: `uiuc-kang-lab/text_to_sql_benchmarks` (A).
- **Kirlenme:** Eğitim verisine sızmış ölçütler skorları şişirir. Kirlenmesiz LiveSQLBench gibi dinamik ölçütler ve kendi veritabanında ölçüm (evalbench, sql-eval) öneriliyor (A).
- **Güncel zorlu ölçütler (A):** Spider 2.0 (Lite'ta en iyi ≈ %44,5), BIRD-CRITIC (hatalı SQL'i düzeltme, en iyi ≈ %43,3), BIRD-INTERACT (çok turlu etkileşim, ödül ≈ 20,9). Bu ölçütler TRSQL'in ilk sürümü için kapsam dışı; tezde bağlam olarak anılabilir.
- **Ret yeteneği (abstention):** EHRSQL, TrustSQL gibi ölçütler yanıtlanamaz sorularda reddi ölçüyor (A). TRSQL'in belirsizlik setine ve "Clarification Rate" metriğine dayanak.
- **Saf Text-to-SQL yetmez:** TAG (Table-Augmented Generation) çalışması, anlamsal çıkarım gerektiren sorularda semantik katman ihtiyacını vurguluyor (A).

**TRSQL için sonuç:** Kurumsal sentetik setin (150–250 soru) her altın SQL'i iki kişi tarafından doğrulanmalı ve Test Suite Accuracy ile birden fazla veri örneğinde ölçülmeli. BIRDTurk sonuçları, BIRD'in etiket hatalarını miras aldığı notuyla raporlanmalı.

### 8(b) Araştırma boşlukları ve hipotezin özgün katkısı

1. **Kurumsal Türkçe ölçüt yok.** Üç Türkçe veri kümesi de İngilizce kaynaklardan çeviri; iş kuralı içeren, Türkçe şemalı ve Türkçe hücre değerli bir set bulunamadı.
2. **Türkçe value linking çalışılmamış.** BIRDTurk hücre değerlerini çevirmediği için ekli Türkçe değerlerin (İstanbul'daki) eşlenmesi hiçbir ölçütte ölçülmemiş.
3. **Belirsizlik ve yanıtsızlık:** Türkçe için hiç veri ve deney bulunamadı.
4. **Küçük model + RAG + doğrulama bileşimi:** 3–9B modellerde katman katman, tekrarlanabilir Türkçe ablasyon yok. En yakın kanıt BIRDTurk'teki DIN-SQL kazancı (Gemini, küçük model değil) ve Hati'nin geri besleme modu (kendi raporu).
5. **Nicemlemenin SQL doğruluğuna etkisi:** SQL'e özgü çalışma yok; genel görevlerde 4-bit küçük modellerde biçim hatası artışı gözlenmiş.
6. **Bağımsız doğrulama:** Hati-Glint-SQL ve Trendyol skorları tek kaynaklı. Tezin ilk katkısı, bu modelleri ve XiYan/Arctic/OmniSQL'i aynı harness ile TURSpider + BIRDTurk dev üzerinde yeniden ölçmek olabilir.

**Hipotezin konumu:** "8 GB tüketici GPU'sunda, katmanlı RAG + deterministik doğrulama ile 3–9B açık model, Türkçe kurumsal sorularda X puan EX'e ulaşır ve tehlikeli SQL'i sıfıra indirir" iddiası boşluk 1, 2, 4 ve 5'i aynı anda hedeflediği için özgündür. Literatürdeki en güçlü destekleyici veri: yapılandırılmış işlem hattının Türkçede İngilizceden iki kat fazla kazandırması (+5,86 vs +2,68).

## Ek A — GitHub proje kataloğu (TRSQL'e uygunluğa göre)

Bu katalog arkadaş raporundaki ~90 depodan TRSQL için anlamlı olanları seçer. Proje açıklamaları ve durum bilgileri **(A)** işaretlidir; yıldız sayıları alınmadı çünkü hızla değişir. "TRSQL'de kullanım" sütunu benim önerimdir. Lisanslar bu turda kontrol edilmedi; bir projeden kod alınmadan önce LICENSE dosyası okunmalı (ADR-0009).

### A.1 Doğrudan kullanılacak veya bağımlılık olabilecek araçlar

| Proje | Ne işe yarar | TRSQL'de kullanım |
| --- | --- | --- |
| [tobymao/sqlglot](https://github.com/tobymao/sqlglot) | Saf Python SQL ayrıştırıcı ve lehçe çevirici | Zaten bağımlılık (`sql_validator`, `policy_engine`) |
| [taoyds/test-suite-sql-eval](https://github.com/taoyds/test-suite-sql-eval) | Spider için Test Suite değerlendiricisi | `benchmarks/` değerlendirme koşucusuna referans |
| [HKUSTDial/NL2SQL360](https://github.com/HKUSTDial/NL2SQL360) | EX, EM, VES, sorgu varyans testi (QVT) | Metrik tanımlarına referans |
| [defog-ai/sql-eval](https://github.com/defog-ai/sql-eval) | PostgreSQL üzerinde canlı değerlendirme, gecikme telemetrisi | Kurumsal set değerlendirmesi için model |
| [uiuc-kang-lab/text_to_sql_benchmarks](https://github.com/uiuc-kang-lab/text_to_sql_benchmarks) | Düzeltilmiş BIRD/Spider 2.0 alt kümeleri | BIRDTurk sonuçlarını temiz alt kümeyle karşılaştırmak |

### A.2 Mimari ve teknik ilham kaynağı (akademik kod)

| Proje | Teknik | İlgili TRSQL modülü |
| --- | --- | --- |
| [ShayanTalaei/CHESS](https://github.com/ShayanTalaei/CHESS) | LSH değer araması, şema budama, revizyon | `rag` (değer arama), `schema_linking` |
| [Laqcce-cao/RSL-SQL](https://github.com/Laqcce-cao/RSL-SQL) | Çift yönlü şema bağlama | `schema_linking` (D2) |
| [BeachWang/DAIL-SQL](https://github.com/BeachWang/DAIL-SQL) | Maskeli iskelet benzerliğiyle few-shot seçimi | `rag` (örnek SQL getirme, D3) |
| [XGenerationLab/XiYan-SQL](https://github.com/XGenerationLab/XiYan-SQL) | M-Schema, çok üreteçli aday + seçici | `prompt_engine` (D1 M-Schema) |
| [MohammadrezaPourreza/Few-shot-NL2SQL-with-prompting](https://github.com/MohammadrezaPourreza/Few-shot-NL2SQL-with-prompting) | DIN-SQL: ayrıştırılmış istem + öz-düzeltme | `query_planner`, onarım döngüsü |
| [wbbeyourself/MAC-SQL](https://github.com/wbbeyourself/MAC-SQL) | Selector / Decomposer / Refiner ajanları | Onarım döngüsü tasarımı (D6) |
| [HKUSTDial/EllieSQL](https://github.com/HKUSTDial/EllieSQL) | Karmaşıklığa göre yönlendirme | D6 mod yönlendirmesi |
| [DEEP-PolyU/KaSLA](https://github.com/DEEP-PolyU/KaSLA) | Token bütçesi altında şema seçimi (knapsack) | `schema_linking`, 4K bağlamda budama |
| [RUCKBReasoning/codes](https://github.com/RUCKBReasoning/codes) | BM25 + LCS değer eşleme | `rag` değer arama alternatifi |
| [ServiceNow/picard](https://github.com/ServiceNow/picard) | Kısıtlı çözme | GBNF deneyi için referans |
| [Snowflake-Labs/ReFoRCE](https://github.com/Snowflake-Labs/ReFoRCE) | Büyük şema sıkıştırma, sütun keşfi | Büyük kurumsal şemalar (sonraki faz) |

### A.3 Açık ağırlıklı modeller ve eğitim çerçeveleri

| Proje | Not | TRSQL'de kullanım |
| --- | --- | --- |
| [RUCKBReasoning/OmniSQL](https://github.com/RUCKBReasoning/OmniSQL) | SynSQL-2.5M ile eğitilmiş 7B/14B/32B (D: makale) | Aday model; sentetik veri yöntemi (AR-06) |
| [snowflakedb/ArcticTraining](https://github.com/snowflakedb/ArcticTraining) | Arctic-Text2SQL-R1 eğitim kodu | Aday model; RL referansı |
| [XGenerationLab/XiYanSQL-QwenCoder](https://github.com/XGenerationLab/XiYanSQL-QwenCoder) | XiYan açık modelleri | Aday model |
| [eosphoros-ai/DB-GPT-Hub](https://github.com/eosphoros-ai/DB-GPT-Hub) | LoRA/QLoRA SFT boru hattı | D7 ince ayar deneyi için şablon |
| [DataArcTech/SQL-R1](https://github.com/DataArcTech/SQL-R1), [ruc-datalab/RewardSQL](https://github.com/ruc-datalab/RewardSQL) | RL tabanlı SQL akıl yürütme | Literatür; 8 GB'ta uygulanmaz |
| [premAI-io/premsql](https://github.com/premAI-io/premsql) | Yerel küçük model boru hattı, sentetik veri | Yerel-öncelikli tasarım için kıyas |

### A.4 Ürün ve platformlar (kıyas ve fikir için, bağımlılık olarak değil)

| Proje | Öne çıkan özellik | TRSQL'e çıkarılacak ders |
| --- | --- | --- |
| [Canner/WrenAI](https://github.com/Canner/WrenAI) | MDL semantik katmanı, MCP sunucusu | `semantic_layer` biçimi |
| [eosphoros-ai/DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | Yerel LLM barındırma, ajan iş akışı | Air-gapped kurulum düzeni |
| [FalkorDB/QueryWeaver](https://github.com/FalkorDB/QueryWeaver) | Graf tabanlı şema, çok atlamalı JOIN | `schema_intelligence` |
| [dataease/SQLBot](https://github.com/dataease/SQLBot) | Terim sözlüğü, çalışma alanı izolasyonu, veri yetkisi | `knowledge_base`, `auth` |
| [OtterMind/Chat2DB](https://github.com/OtterMind/Chat2DB) | Yerel istemci, şifreli kimlik bilgisi saklama | L0 ve gizli bilgi yönetimi |
| [vanna-ai/vanna](https://github.com/vanna-ai/vanna) | DDL + doküman + "golden SQL" RAG (arkadaş raporu: 2026'da arşivlendi, A) | Golden SQL havuzu fikri |
| [googleapis/mcp-toolbox](https://github.com/googleapis/mcp-toolbox) | MCP veritabanı kontrol düzlemi, OpenTelemetry | TRSQL'i dışarıya MCP aracı olarak açma (AR-10 sonrası) |
| [ashishsinha1602/schemagate](https://github.com/ashishsinha1602/schemagate) | Rol bazlı şema seçimi + RLS | `auth.scope_schema()` ile karşılaştırma |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | İstem derleme, few-shot optimizasyonu | `prompt_engine` şablon ayarı (deneysel) |

### A.5 El kitapları

[HKUSTDial/NL2SQL_Handbook](https://github.com/HKUSTDial/NL2SQL_Handbook) · [DEEP-PolyU/Awesome-LLM-based-Text2SQL](https://github.com/DEEP-PolyU/Awesome-LLM-based-Text2SQL) · [eosphoros-ai/Awesome-Text2SQL](https://github.com/eosphoros-ai/Awesome-Text2SQL) · [HKUSTDial/awesome-data-agents](https://github.com/HKUSTDial/awesome-data-agents) (A)

## Kaynaklar

Arkadaş raporunun kaynakçası (konferans makaleleri ve GitHub depoları) Ek A'daki bağlantılarda yer alır; aşağıdaki liste Claude raporunun kaynaklarıdır.

Bu turda açılıp okunanlar (D):

- [BIRDTurk, ACL Anthology](https://aclanthology.org/2026.sigturk-1.13/) · [arXiv 2602.03633](https://arxiv.org/abs/2602.03633v1) · [GitHub](https://github.com/metunlp/birdturk)
- [TURSpider, İTÜ araştırma portalı](https://research.itu.edu.tr/en/publications/turspider-a-turkish-text-to-sql-dataset-and-llm-based-study/)
- [TUR2SQL, İTÜ portalı](https://research.itu.edu.tr/en/publications/tur2sql-a-cross-domain-turkish-dataset-for-text-to-sql/) · [GitHub](https://github.com/alibugra/TUR2SQL)
- HF kartları: [XiYanSQL 3B](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-3B-2504), [7B](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-7B-2504), [32B](https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-32B-2504); [OmniSQL-7B](https://huggingface.co/seeklhy/OmniSQL-7B), [OmniSQL-32B](https://huggingface.co/seeklhy/OmniSQL-32B); [Arctic-Text2SQL-R1-7B](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B); [Qwen2.5-Coder-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct); [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507); [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B); [Hati-Glint-SQL-9B-v1](https://huggingface.co/runelab-ai/Hati-Glint-SQL-9B-v1); [sqrl-9b](https://huggingface.co/feyninc/sqrl-9b)
- [Qwen2.5-Coder ailesi blog yazısı (lisans tablosu)](https://qwenlm.github.io/blog/qwen2.5-coder-family/)
- [Trendyol-LLM-8B-T1 README (Featherless kopyası)](https://featherless.ai/models/Trendyol/Trendyol-LLM-8B-T1/readme)
- [Licardo & Tankovic 2025, arXiv 2510.21970](https://arxiv.org/pdf/2510.21970)
- [Zhang 2026, Research Square ön baskı](https://www.researchsquare.com/article/rs-11704703/v1)

Künyesi bellekten verilen, bu turda açılmayanlar (B): WikiSQL, Spider, BIRD, Spider 2.0, PICARD, RESDSQL, DIN-SQL, DAIL-SQL, CHESS, CHASE-SQL, XiYan-SQL makalesi, Test Suite Accuracy, OWASP LLM Top 10, PostgreSQL belgeleri, KVKK md. 9. Model config değerleri (katman/KV-head) ve GPU bant genişliği de bellektendir.

27 Kasım'da eklenenler: [BIRDTurk HF veri kümesi](https://huggingface.co/datasets/metunlp/birdturk/blob/main/dev/dev_tr.json) (D), [Jin vd. 2026, arXiv 2601.08778](https://arxiv.org/abs/2601.08778) (D, özet). Seydi'nin paylaştığı rapordan alınıp bu turda açılmayanlar: TURSpider HF lisansı, Chavan 2026, Beurer-Kellner vd. 2024, KVKK rehberinin içeriği.

Alt başlık düzenlemesinde eklenenler (D): [OmniSQL makalesi](https://arxiv.org/html/2503.02240v2), [Afrin vd. 2026, nicemleme ve kod üretimi](https://arxiv.org/pdf/2607.14181), [Fang vd. 2025](https://arxiv.org/pdf/2506.22776), [Red Hat vLLM vs llama.cpp](https://developers.redhat.com/articles/2025/09/30/vllm-or-llamacpp-choosing-right-llm-inference-engine-your-use-case), [llmconfigurator RTX 4070 Laptop tahmini](https://llmconfigurator.com/en/upgrade/laptop-rtx-4070-8gb/to-run-qwen3-8b).
