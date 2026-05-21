# RAG Integration Summary

## چه کاری انجام شد

1. **پشتیبانی از آپلود فایل برای RAG**
   - مسیر جدید `POST /api/v1/files?process=true` اضافه شد.
   - فایل‌ها روی سرور ذخیره می‌شوند و پردازش می‌شوند.
   - متن فایل‌ها به قطعات کوچک‌تر (`chunks`) تقسیم می‌شود.

2. **semantic retrieval برای RAG**
   - برای هر chunk embedding با `HashingVectorizer` ساخته می‌شود.
   - query کاربر به صورت semantic با chunkها مقایسه می‌شود.
   - بهترین chunk‌های مرتبط انتخاب شده و به prompt مدل اضافه می‌شوند.

3. **فرمت‌های پشتیبانی‌شده**
   - فایل‌های متنی و code: `.txt`, `.md`, `.csv`, `.json`, `.py`, `.c`, `.cpp`, `.h`
   - فایل‌های تصویری: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.tif`, `.webp`
   - PDF با `pypdf`

4. **بهبود prompt template برای context injection**
   - متن RAG به prompt سیستم اضافه می‌شود.
   - دستور داده شده که تنها در صورت مرتبط بودن استفاده شود.
   - اگر context مرتبط نباشد، مدل باید پاسخ عمومی بدهد.

5. **token و score tuning**
   - آستانه `RAG_MIN_SCORE` کاهش یافت تا فایل‌های کوتاه‌تر بهتر بازیابی شوند.
   - ترکیب امتیاز semantic و lexical اجرا شد تا بازیابی دقیق‌تر شود.

6. **احراز هویت**
   - `POST /api/v1/auth/login` برای گرفتن JWT اضافه شد.
   - `POST /api/v1/files` با JWT محافظت می‌شود.
   - `POST /v1/chat/completions` با `X-API-Key` کار می‌کند.

## چه قابلیت‌هایی اضافه شد

- RAG فایل‌های آپلودشده
- semantic retrieval با `scikit-learn`
- context injection در prompt
- ذخیره chunk و embedding در دیتابیس
- fallback lexical برای زمانی که semantic ضعیف است
- مدیریت فایل RAG از طریق جدول‌های `rag_file` و `rag_chunk`

## چگونه از آن استفاده می‌شود

1. با `POST /api/v1/auth/login` وارد شو و `access_token` بگیر.
2. فایل را با `POST /api/v1/files?process=true` و هدر `Authorization: Bearer <JWT>` آپلود کن.
3. شناسه فایل (`file_id`) را بگیر.
4. چت را با `POST /v1/chat/completions` بزن و در body فیلد `files` را ارسال کن:
   ```json
   "files": [{ "id": "<FILE_ID>", "type": "rag", "name": "file.txt" }]
   ```
5. مدل پاسخ را بر اساس متن بازیابی شده می‌دهد.

## فرق با OpenWebUI

- این پروژه backend ریز و RAG-specific دارد.
- OpenWebUI معمولاً frontend است و ممکن فقط درخواست استاندارد OpenAI بفرستد.
- اگر OpenWebUI request را به `http://localhost:8001/v1/chat/completions` بفرستد، چت معمولی کار می‌کند.
- اگر بخواهی RAG استفاده شود، باید `files` هم ارسال شود یا رابطی ایجاد شود که فایل را به `POST /api/v1/files` آپلود کند.

## نکته مهم

- فایل‌ها در backend ذخیره و پردازش می‌شوند.
- این فایل‌ها فقط وقتی در `files` request chat می‌آیند، مورد استفاده قرار می‌گیرند.
- اگر `files` نباشد، چت مثل یک چت ساده بدون RAG خواهد بود.

## فایل‌های کلیدی تغییر یافته

- `app/services/rag_service.py`
- `app/services/chat_completion_service.py`
- `app/core/security.py`
- `app/config.py`
- `requirements.txt`

## وضعیت فعلی

- RAG روی فایل آپلودشده کار می‌کند.
- retrieval و prompt injection فعال است.
- auth و dependency لازم نصب و اصلاح شدند.
- برای OpenWebUI اگر بخواهد از RAG استفاده کند، باید request حاوی `files` به این backend ارسال کند.
