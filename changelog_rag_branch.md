# Changelog — Rag Branch (۳ commit آخر)

---

## Commit 1: `c6d9f18` — add tokenizer to optimize max_token

| فایل | تغییر |
|------|-------|
| `app/services/token_utils.py` | **فایل جدید** — تخمین دقیق‌تر token با regex |
| `app/services/chat_completion_service.py` | جایگزینی `len(text)//3` با `estimate_text_tokens()` |
| `app/runtime/vllm_http_generator.py` | لاگ‌ها از تخمین دقیق token استفاده می‌کنند |

### تغییرات:
- حذف `len(text) // 3` و جایگزینی با توکنایزر مبتنی بر regex که کلمات بلند را به زیربخش‌های ۴ تایی تقسیم می‌کند.
- اضافه شدن `safety_margin=64` به جای `512` برای جلوگیری از overflow.
- `max_output_tokens` به صورت داینامیک بر اساس حجم واقعی prompt تنظیم می‌شود (نه فقط budget).
- حذف call اضافی `_trim_messages_to_budget()` بعد از تنظیم دقیق prompt_tokens.

---

## Commit 2: `5532183` — reriev_contetx to verify source with prompt

| فایل | تغییر |
|------|-------|
| `app/services/rag_service.py` | بهبود `retrieve_context()` |

### تغییرات:
- اگر هیچ chunk با relevance > 0 پیدا نشود، به جای fallback به همه chunks، **خالی برمی‌گرداند**.
- این کار باعث می‌شود مدل فقط وقتی context دریافت کند که واقعاً مرتبط باشد.

---

## Commit 3: `359bdbc` — feat: enhance RAG with semantic retrieval, fix password auth

| فایل | تغییر |
|------|-------|
| `app/services/rag_service.py` | **بازنویسی عمده** سیستم retrieval |
| `app/core/security.py` | پشتیبانی از Django pbkdf2_sha256 + bcrypt |
| `app/config.py` | اضافه شدن `RAG_MIN_SCORE`, `RAG_MAX_CONTEXT_TOKENS`, `RAG_EMBEDDING_DIM` |
| `app/services/chat_completion_service.py` | بهبود prompt RAG |
| `requirements.txt` | اضافه شدن `scikit-learn` |
| `RAG_implementation_summary.md` | فایل مستندات جدید |

### ۳.۱ — Semantic Retrieval (`rag_service.py`)
- `HashingVectorizer(sklearn)` جایگزین روش purely lexical شد.
- برای هر chunk در زمان `ingest_rag_file()` embedding محاسبه و در `metadata_["embedding"]` ذخیره می‌شود.
- در `retrieve_context()`، query هم embedding می‌شود و با **cosine similarity** مقایسه می‌شود.
- نمره نهایی ترکیبی از semantic و lexical است: `max(cosine_similarity, lexical_score)`.
- تابع `_score()` از boolean-match → **relative match** (نسبت terms منطبق) تغییر کرد.
- آستانه `RAG_MIN_SCORE` برای query کوتاه (≤۳ کلمه) به `max(0.10, 0.5)` افزایش می‌یابد.
- `RAG_MAX_CONTEXT_TOKENS=2048` برای محدودیت token budget context اضافه شد.

### ۳.۲ — Password Auth (`security.py`)
- CryptContext اکنون از `django_pbkdf2_sha256` و `bcrypt` پشتیبانی می‌کند.
- خطای `UnknownHashError` هندل می‌شود و `False` برمی‌گرداند.

### ۳.۳ — Prompt بهبودیافته
- متن جدید: "Use this context only when it directly supports the user query. If the context is not relevant, do not force it into the answer."

### ۳.۴ — Config
- `RAG_MIN_SCORE: float = 0.10`
- `RAG_MAX_CONTEXT_TOKENS: int = 2048`
- `RAG_EMBEDDING_DIM: int = 512`

---

## خلاصه کل تغییرات Rag Branch (از ابتدا)

| تاریخ | commit | عنوان |
|-------|--------|-------|
| May 21, 05:44 | `359bdbc` | feat: enhance RAG with semantic retrieval, fix password auth |
| May 21, 03:58 | `5532183` | reriev_contetx to verify source with prompt |
| May 21, 03:40 | `c6d9f18` | add tokenizer to optimize max_token |
| May 21, 03:04 | `c636db5` | fix(rag): enable configurable EasyOCR GPU usage |
| May 20, 05:22 | `029c305` | feat: increase max_tokens default, add image/OCR support, fix logging |
| May 19, 21:40 | `6d1c17d` | add upload file and fix chat conversation send from openweb ui |
| May 19, 20:26 | `e0b89f6` | Prevent Open WebUI metadata tasks from polluting chat history |
| May 18, 01:54 | `6618787` | Initial FastAPI LLM server |

---

## آموزش: دستورات مفید git برای مشاهده تغییرات

```bash
# مشاهده تاریخچه
git log Rag --oneline -5

# مشاهده گرافیکی
git log Rag --oneline --graph

# جزئیات کامل یک commit
git show <commit-hash>

# فایل‌های تغییر یافته در یک commit
git show <commit-hash> --stat

# مقایسه دو commit
git diff <commit1>..<commit2>

# مقایسه با HEAD
git diff <commit>..HEAD

# تغییرات commit آخر نسبت به یکی قبل
git diff <commit>~1..<commit>
```
