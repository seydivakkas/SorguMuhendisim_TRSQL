# Değerlendirme Planı

İlke 10 (**Benchmark-driven**): teknoloji kararları ölçülebilir deneylere dayanır. Bu
plan; metrikleri, veri kümelerini, D0–D8 ablasyon basamaklarını, donanım ölçümünü ve
tekrarlanabilirlik protokolünü tanımlar.

## 1. Metrikler

| Metrik | Tanım | Katman | Hedef (ilk tahmin, AR-08'de güncellenir) |
|---|---|---|---|
| **Execution Accuracy (EX)** | Üretilen SQL'in sonuç kümesinin altın SQL sonucuyla eşleşme oranı (satır sırası yalnız `ORDER BY` varsa önemli) | Uçtan uca | Temel çizgiye (D0) göre anlamlı artış |
| **Schema Linking Accuracy** | Seçilen tablo/sütunların altın SQL'dekilerle precision / recall / F1'i | L3 | Recall ≥ 0,95 (eksik tablo telafi edilemez) |
| **Retrieval Recall@K** | İlgili iş kuralı/örneğin ilk K sonuçta bulunma oranı | L4 | K=5 için ≥ 0,9 |
| **Valid SQL Rate** | Sözdizimsel olarak geçerli ve şemayla tutarlı SQL oranı | L5/L6 | ≥ 0,95 |
| **Latency** | İstek başına p50 / p95 süre; aşama kırılımıyla | Tümü | p95 < 15 sn (referans dizüstü) |
| **VRAM / RAM Usage** | Tepe VRAM ve RAM; model yükleme + KV cache | L5 | VRAM ≤ 6,8 GB |
| **Security Violation Rate** | `REJECTED` sonuçlanan isteklerin oranı (meşru sorularda ≈ 0 olmalı) ve saldırı setinde yakalama oranı (= 1 olmalı) | L6 | Saldırı yakalama = %100 |
| **Retry Rate** | 1'den fazla deneme gerektiren isteklerin oranı ve ortalama deneme sayısı | L5/L6 | Raporlanır |
| **Clarification Rate** | `NEEDS_CLARIFICATION` oranı (belirsizlik setinde doğruluk) | L2 | Raporlanır |
| **Token/s, enerji** | Üretim hızı; mümkünse enerji tüketimi | L5 | Raporlanır |

Tüm metrikler soru zorluğuna (kolay/orta/zor/ekstra) ve soru tipine (intent) göre
kırılımlı raporlanır.

## 2. Veri kümeleri ve kullanım izni

| Küme | Dil | Kullanım | Not |
|---|---|---|---|
| TURSpider (dev) | Türkçe | Değerlendirme | Ana Türkçe karşılaştırma ölçütü |
| BIRDTurk (dev) | Türkçe | **Yalnız değerlendirme** | HF kartı cc-by-nc-sa-4.0 → eğitimde kullanılmaz (ADR-0009). Şema adları Türkçe, hücre değerleri çevrilmemiş. |
| Spider / BIRD (dev) | İngilizce | Değerlendirme, karşılaştırma | Literatürle karşılaştırılabilirlik |
| Kurumsal sentetik set | Türkçe | Değerlendirme (+ ayrı bölüm eğitim) | 150–250 soru, PostgreSQL, iş kuralları ve RBAC senaryolarıyla (`synthetic_data/`) |
| Güvenlik saldırı seti | Türkçe | Değerlendirme | İstem enjeksiyonu, yetkisiz erişim, DoS kalıpları; `tests/security` örneklerinden büyütülür |
| Belirsizlik seti | Türkçe | Değerlendirme | Netleştirme gerektiren sorular (L2) |

Eğitim ve değerlendirme kümeleri arasında veritabanı düzeyinde ayrım yapılır
(aynı veritabanı iki tarafta bulunmaz).

## 3. D0–D8 ablasyon basamakları

Basamaklar **kümülatiftir**: her basamak öncekinin üzerine tek bir bileşen ekler; böylece
her bileşenin katkısı ayrı ölçülür. Her basamak tüm aday modellerle koşturulur.

| Basamak | Eklenen bileşen | Katman / modül | AR |
|---|---|---|---|
| **D0** | Ham LLM + DDL şeması (temel çizgi) | L5 | AR-02 |
| **D1** | M-Schema biçiminde şema sunumu | `prompt_engine` | AR-02 |
| **D2** | Schema linking + FK Steiner grafı (yalnız ilgili tablolar) | L3 | AR-03 |
| **D3** | Çoklu RAG: iş kuralları + örnekler + LSH değer araması (BGE-M3, CPU) | L4 | AR-04 |
| **D4** | Türkçe NLP + belirsizlik tespiti | L2 | AR-03 |
| **D5** | Fail-closed güvenlik (L6 tam + L7) | L6/L7 | AR-07 |
| **D6** | Doğrudan → düşünerek (thinking) yönlendirme + onarım döngüsü | L5/orchestration | AR-05 |
| **D7** | Gerekirse PostgreSQL odaklı QLoRA / RAFT ince ayarı | `model_engine` | AR-06 |
| **D8** | Tam hibrit sistem | Tümü | AR-09 |

Not: D5 doğruluğu düşürebilir (fail-closed). Bu beklenen bir bedeldir ve ayrıca raporlanır.

## 4. Aday modeller

| Model | Neden aday | Not |
|---|---|---|
| Hati-Glint-SQL-9B | TURSpider/BIRDTurk skoru yayımlanmış tek Türkçe SQL modeli | Skorlar kendi beyanı; bağımsız doğrulanacak |
| Arctic-Text2SQL-R1-7B | Güçlü açık Text-to-SQL modeli | Türkçe performansı ölçülecek |
| XiYanSQL-QwenCoder-7B | Güçlü açık Text-to-SQL modeli | Türkçe performansı ölçülecek |
| Küçük (≈3B) kontrol modeli | Small Model-first alt sınırı | Lisans kontrolü (ör. Qwen2.5-Coder-3B `qwen-research`) |

Tümü 4-bit GGUF olarak ≈6,8 GB net VRAM bütçesinde çalışmalıdır. Bütçeyi aşan
konfigürasyon "uygun değil" olarak raporlanır, elenir.

## 5. Donanım ve ortam

- Referans makine: RTX 4070 Laptop (8 GB VRAM), 32 GB RAM, Windows.
- Her koşuda kaydedilir: GPU sürücüsü, CUDA, çıkarım çalışma zamanı sürümü, quantization,
  bağlam uzunluğu, batch, iş parçacığı sayısı, güç modu (prize takılı).
- VRAM ölçümü: tepe değer (`nvidia-smi` örneklemesi) ve model yükleme sonrası sabit değer.

## 6. Tekrarlanabilirlik protokolü

Her deney `experiments/<tarih>-<kısa-ad>/` altında şunları içerir:

1. `config.toml` — basamak (D0–D8), model + quantization, istem `template_id`, retriever
   ayarları, `retry.max_attempts`, seed.
2. Veri kümesi adı, sürümü ve dosya hash'i.
3. Git commit hash'i (kirli çalışma ağacında deney koşulmaz).
4. Ham tahminler (`predictions.jsonl`) ve metrik özeti (`metrics.json`).
5. Donanım bilgisi ve süreler.
6. Kısa yorum: beklenti, sonuç, sonraki adım.

Kod çözme varsayılan olarak deterministiktir (temperature 0). Örnekleme kullanılan
deneylerde en az 3 seed ile ortalama ± std raporlanır. Basamaklar arası farklar için
eşleştirilmiş anlamlılık testi (ör. McNemar) uygulanır.

## 7. Raporlama

- Ana tablo: model × basamak (D0–D8) × veri kümesi → EX, Valid SQL Rate, p95 Latency, VRAM.
- Bileşen katkısı: ardışık basamaklar arası Δ EX.
- Güvenlik tablosu: saldırı seti yakalama oranı, meşru sorularda yanlış ret oranı.
- Hata analizi: en az 50 başarısız örnek elle etiketlenir (linking, mantık, Türkçe, değer,
  JOIN, toplama, zaman).

## 8. Kabul kapıları (gates)

| Gate | Koşul | Ne zaman |
|---|---|---|
| G1–G5 | Lint, tip, sınır, güvenlik ve tüm testler geçer | Her PR (CI) |
| E1 | Yeni bileşen, önceki basamağa göre EX'i düşürmez **veya** düşüşü güvenlik/açıklanabilirlik kazancıyla gerekçelendirilir | Bileşen birleştirilmeden önce |
| E2 | Saldırı setinde yakalama oranı %100 | Her sürüm |
| E3 | VRAM ≤ bütçe, p95 gecikme hedefte | Model/çalışma zamanı kararı öncesi |
