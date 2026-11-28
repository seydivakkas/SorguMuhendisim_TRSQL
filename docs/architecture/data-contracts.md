# Veri Sözleşmeleri

Modüller arasında geçen **tek** veri türü, `backend/core/contracts.py` içindeki Pydantic
sözleşmeleridir. Arayüzler (port) `backend/core/ports.py` içindedir.

## Kurallar

1. Her sözleşme `Contract` sınıfından türer: `frozen=True` (değiştirilemez),
   `extra="forbid"` (bilinmeyen alan reddedilir).
2. Bir modül başka bir modülün iç sınıfını parametre ya da dönüş tipi olarak kullanamaz;
   yalnızca `core` sözleşmeleri kullanılır.
3. Sözleşme değişikliği **kırıcı değişiklik**tir: PR açıklamasında belirtilir, bu doküman
   güncellenir, gerekiyorsa ADR yazılır.
4. Alan adları İngilizce, kullanıcıya dönen metinler (mesaj, açıklama) Türkçedir.
5. Tarih aralıkları `[start, end)` (başlangıç dahil, bitiş hariç).

## Katman → sözleşme haritası

| Katman | Üretilen sözleşme | Tüketen | Önemli alanlar |
|---|---|---|---|
| L1 | `AuthContext` | tüm aşamalar | `user_id`, `tenant_id`, `roles`, `allowed_tables`, `denied_columns`, `max_rows` |
| L1 | `QueryRequest` | orchestration | `request_id`, `question` (≤2000), `connection_id` |
| DB | `SchemaSnapshot` (`TableInfo`, `ColumnInfo`, `ForeignKey`) | auth, L3, L5, L6 | `dialect`, `tables` |
| L2 | `ParsedQuestion` (`Mention`, `TemporalExpression`) | L3, L4, L5, L8 | `intent`, `mentions`, `temporal`, `sort`, `limit`, `ambiguities` |
| L3 | `LinkedSchema` (`SchemaLink`, `JoinStep`) | L4, L5 | `tables`, `links[score]`, `join_path` |
| L4 | `KnowledgeContext` (`BusinessRule`, `MetricDefinition`, `FewShotExample`) | L5 | yalnız `approved=True` kurallar; metrikler sürümlü |
| L5 | `QueryPlan` | prompt_engine, L8 | `intent`, `tables`, `metrics`, `filters`, `temporal`, `sort`, `limit` |
| L5 | `PromptBundle` | ModelAdapter | `template_id` (sürüm), `system`, `user` |
| L5 | `SQLCandidate` | L6 | `sql`, `dialect`, `model_id`, `attempt`, `latency_ms` — **güvenilmeyen girdi** |
| L6 | `ValidationReport` (`CheckResult`) | orchestration, policy | `checks[]`, türetilmiş `verdict` |
| L6 | `ApprovedQuery` | L7 | onaysız rapordan **oluşturulamaz**; `max_rows`, `timeout_ms`, `auth` (onaylanan kimlik: SQLite yetkilendirici izin listesi ve PostgreSQL RLS bağlamı için) |
| L7 | `ExecutionResult` | L8 | `columns`, `rows`, `truncated`, `elapsed_ms` |
| L8 | `ResultReport` (`ChartSpec`) | L0 | `summary` (Türkçe), `chart`, `sql`, `metrics_used` |
| — | `PipelineOutcome` | L0 | `status`, `attempts`, `report` / `clarification` / `reason` |
| L9 | `AuditEvent` | AuditSink | `stage`, `status`, maskelenmiş `details` |

## Doğrulama kararı (verdict)

```text
herhangi bir başarısız kontrol SECURITY   → REJECTED
aksi halde başarısız kontrol REPAIRABLE   → REPAIRABLE
hepsi geçti                                → APPROVED
```

`verdict` saklanan bir alan değil, `checks` üzerinden **hesaplanan** bir özelliktir;
böylece bir modül raporu "onaylı" diye işaretleyemez.

## Portlar (arayüzler)

| Port | Uygulayan modül | Not |
|---|---|---|
| `ModelAdapter` | `model_engine` (`FakeModelAdapter`, `LlamaCppAdapter`) | `info`, `generate(prompt, params) -> str`. DB erişimi yok. |
| `DatabaseAdapter` | `database_adapters` (`SQLiteAdapter`, `PostgresAdapter`) | `introspect()`, `execute(ApprovedQuery)` |
| `AuditSink` | `observability` | `emit(AuditEvent)` |
| `QuestionParser` | `turkish_nlp` | |
| `SchemaLinker` | `schema_linking` | |
| `KnowledgeProvider` | `orchestration.KnowledgeAssembler` (rag + semantic_layer) | |
| `QueryPlannerPort` | `query_planner` | |
| `PromptBuilderPort` | `prompt_engine` | |
| `SQLGeneratorPort` | `sql_generator` | |
| `SQLValidatorPort` | `sql_validator` | tam şema + AuthContext alır |
| `PolicyEnforcer` | `policy_engine` | tek `ApprovedQuery` üreticisi |
| `QueryExecutor` | `execution_engine` | |
| `ResultBuilderPort` | `result_engine` | |

Bir aşamayı değiştirmek (ör. Zemberek tabanlı ayrıştırıcı, hibrit linker, farklı model),
aynı portu uygulayan yeni bir sınıf yazıp `build_default_pipeline` içinde bağlamaktan
ibarettir. Diğer modüller değişmez.
