# داشبورد ادمین LLM

داشبورد وب اختصاصی برای مدیریت کاربران، کلیدهای API و مشاهده مصرف توکن در سرویس `llm_fastapi`.

## پیش‌نیازها

- کاربری با `is_superuser=True` در پایگاه داده
- Redis برای ذخیره مصرف ماهانه (`quota:{api_key_id}:{YYYY-MM}`)
- Node.js 18+ برای ساخت فرانت‌اند

## راه‌اندازی

### ۱. ساخت فرانت‌اند

```bash
cd admin
npm install
npm run build
```

خروجی در `admin/dist` قرار می‌گیرد و توسط FastAPI در مسیر `/admin` سرو می‌شود.

### ۲. اجرای سرور

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### ۳. ورود به داشبورد

مرورگر: `http://HOST:8001/admin`

با نام کاربری و رمز عبور یک **superuser** وارد شوید. کاربران عادی خطای 403 دریافت می‌کنند.

## توسعه محلی (فرانت‌اند)

```bash
cd admin
npm install
npm run dev
```

Vite روی پورت 5173 اجرا می‌شود و درخواست‌های `/api` را به `http://127.0.0.1:8001` پروکسی می‌کند.

## API ادمین

همه endpointها زیر `/api/v1/admin` و با JWT Bearer + `require_superuser`:

| متد | مسیر | توضیح |
|-----|------|--------|
| GET | `/users` | لیست کاربران |
| POST | `/users` | ساخت کاربر |
| PATCH | `/users/{id}` | فعال/غیرفعال، ایمیل |
| GET | `/api-keys` | لیست کلیدها (`?user_id=`) |
| POST | `/api-keys` | ساخت کلید برای کاربر |
| PATCH | `/api-keys/{id}` | لغو / تغییر محدودیت‌ها |
| GET | `/usage` | خلاصه مصرف ماه جاری |
| GET | `/usage/{api_key_id}` | جزئیات مصرف یک کلید |

## صفحات داشبورد

1. **کاربران** — ساخت کاربر جدید، فعال/غیرفعال‌سازی
2. **کلیدهای API** — ساخت کلید برای هر کاربر، نمایش یک‌باره `raw_key`، ویرایش سهمیه/محدودیت، لغو کلید
3. **مصرف توکن** — جدول مصرف ماهانه با نوار پیشرفت نسبت به سهمیه

## ساخت superuser اولیه

اگر superuser ندارید، از Django shell، SQL مستقیم، یا پس از bootstrap اولین کاربر از طریق API (با یک superuser موجود) استفاده کنید. فیلد `is_superuser` در جدول `users_user` باید `true` باشد.

## ثبت مصرف توکن

مصرف در Redis پس از هر درخواست chat/completions ثبت می‌شود:

- `/v1/chat/completions` (غیر-stream و stream)
- `/code_bot/v1/chat/completions` (غیر-stream و stream)

کلید Redis: `quota:{api_key_id}:{YYYY-MM}`

## نکات امنیتی

- فقط superuser به API ادمین دسترسی دارد
- کلیدهای API برای نمایش در پنل ادمین **رمزنگاری‌شده** در DB ذخیره می‌شوند (`key_encrypted`) و فقط superuser می‌تواند آن‌ها را ببیند
- کلیدهای قدیمی (قبل از این قابلیت): `python3 scripts/backfill_key_hints.py` از فایل‌های تنظیمات محلی بازیابی می‌کند
- `raw_key` فقط هنگام ساخت کلید یک‌بار برگردانده می‌شود
- JWT در `localStorage` مرورگر ذخیره می‌شود (برای محیط production از HTTPS استفاده کنید)
