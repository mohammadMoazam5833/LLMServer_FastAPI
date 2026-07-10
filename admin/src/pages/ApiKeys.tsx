import { FormEvent, useEffect, useState } from "react";
import { api, AdminAPIKey, AdminUser, ApiError } from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import Alert from "../components/ui/Alert";
import PageShell from "../components/ui/PageShell";
import {
  FormCard,
  FormField,
  FormRow,
  FormCol,
  FormSubmitCol,
  Input,
  Select,
  PrimaryButton,
  GhostButton,
} from "../components/ui/Form";
import { Card, CardBody, CardHeader } from "../components/ui/Card";

export default function ApiKeys() {
  const [keys, setKeys] = useState<AdminAPIKey[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [rawKey, setRawKey] = useState<string | null>(null);

  const [userId, setUserId] = useState("");
  const [name, setName] = useState("");
  const [rateLimit, setRateLimit] = useState("180");
  const [quota, setQuota] = useState("1000000");
  const [filterUserId, setFilterUserId] = useState("");
  const [creating, setCreating] = useState(false);
  const [editingKey, setEditingKey] = useState<AdminAPIKey | null>(null);
  const [editRateLimit, setEditRateLimit] = useState("");
  const [editQuota, setEditQuota] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [userList, keyList] = await Promise.all([
        api.listUsers(),
        api.listApiKeys(
          filterUserId ? Number(filterUserId) : undefined,
        ),
      ]);
      setUsers(userList);
      setKeys(keyList);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در بارگذاری");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [filterUserId]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!userId) return;
    setCreating(true);
    setError("");
    try {
      const created = await api.createApiKey({
        user_id: Number(userId),
        name,
        rate_limit_per_minute: Number(rateLimit),
        monthly_token_quota: Number(quota),
      });
      setRawKey(created.raw_key);
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در ساخت کلید");
    } finally {
      setCreating(false);
    }
  }

  async function revokeKey(key: AdminAPIKey) {
    if (!confirm("این کلید غیرفعال شود؟")) return;
    setError("");
    try {
      await api.updateApiKey(key.id, { is_active: false });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در لغو کلید");
    }
  }

  function openEdit(key: AdminAPIKey) {
    setEditingKey(key);
    setEditRateLimit(String(key.rate_limit_per_minute));
    setEditQuota(String(key.monthly_token_quota));
  }

  function closeEdit() {
    setEditingKey(null);
    setEditRateLimit("");
    setEditQuota("");
  }

  async function handleSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editingKey) return;
    setSaving(true);
    setError("");
    try {
      await api.updateApiKey(editingKey.id, {
        rate_limit_per_minute: Number(editRateLimit),
        monthly_token_quota: Number(editQuota),
      });
      closeEdit();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در به‌روزرسانی");
    } finally {
      setSaving(false);
    }
  }

  function copyRawKey() {
    if (rawKey) {
      navigator.clipboard.writeText(rawKey);
    }
  }

  function copyKey(key: string) {
    navigator.clipboard.writeText(key);
  }

  return (
    <PageShell>
      <PageHeader
        title="کلیدهای API"
        subtitle={`${keys.filter((k) => k.is_active).length} کلید فعال — برای OpenWebUI، Cline و OpenHands`}
      />
      <Alert message={error} />

      {editingKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 backdrop-blur-sm px-4">
          <form
            onSubmit={handleSaveEdit}
            className="w-full max-w-md bg-white rounded-xl border border-zinc-200 p-6 space-y-5 shadow-2xl"
          >
            <h3 className="font-bold text-zinc-900 text-lg">ویرایش محدودیت‌ها</h3>
            <p className="text-sm text-zinc-600 leading-relaxed">
              کلید: <strong className="text-zinc-800">{editingKey.name || editingKey.id}</strong>
              <span className="text-zinc-400"> · </span>
              {editingKey.username}
            </p>
            <FormField label="محدودیت درخواست در دقیقه">
              <Input type="number" value={editRateLimit} onChange={(e) => setEditRateLimit(e.target.value)} min={0} required />
            </FormField>
            <FormField label="سهمیه ماهانه توکن (۰ = بدون محدودیت)">
              <Input type="number" value={editQuota} onChange={(e) => setEditQuota(e.target.value)} min={0} required />
            </FormField>
            <div className="flex gap-3 justify-end pt-2">
              <GhostButton type="button" onClick={closeEdit}>انصراف</GhostButton>
              <PrimaryButton type="submit" disabled={saving}>{saving ? "ذخیره…" : "ذخیره"}</PrimaryButton>
            </div>
          </form>
        </div>
      )}

      {rawKey && (
        <div className="bg-violet-50 border border-violet-200/80 rounded-xl p-6 space-y-4">
          <p className="text-sm font-semibold text-violet-900">
            کلید جدید ساخته شد — همین الان کپی کنید
          </p>
          <code className="block text-xs break-all bg-white p-4 rounded-lg border border-violet-100 font-mono text-zinc-800">
            {rawKey}
          </code>
          <div className="flex gap-3">
            <PrimaryButton type="button" onClick={copyRawKey}>
              کپی کلید
            </PrimaryButton>
            <GhostButton type="button" onClick={() => setRawKey(null)}>
              بستن
            </GhostButton>
          </div>
        </div>
      )}

      <FormCard title="ساخت کلید API جدید" subtitle="برای OpenWebUI، Cline، OpenHands و Agent Canvas">
        <form onSubmit={handleCreate}>
          <FormRow>
            <FormCol span={3}>
              <FormField label="کاربر">
                <Select value={userId} onChange={(e) => setUserId(e.target.value)} required>
                  <option value="">انتخاب…</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.username}</option>
                  ))}
                </Select>
              </FormField>
            </FormCol>
            <FormCol span={2}>
              <FormField label="نام کلید">
                <Input placeholder="cline" value={name} onChange={(e) => setName(e.target.value)} />
              </FormField>
            </FormCol>
            <FormCol span={2}>
              <FormField label="محدودیت / دقیقه">
                <Input type="number" value={rateLimit} onChange={(e) => setRateLimit(e.target.value)} min={1} />
              </FormField>
            </FormCol>
            <FormCol span={2}>
              <FormField label="سهمیه ماهانه">
                <Input type="number" value={quota} onChange={(e) => setQuota(e.target.value)} min={0} />
              </FormField>
            </FormCol>
            <FormSubmitCol span={3}>
              <PrimaryButton type="submit" disabled={creating} className="w-full">
                {creating ? "در حال ساخت…" : "+ ساخت کلید"}
              </PrimaryButton>
            </FormSubmitCol>
          </FormRow>
        </form>
      </FormCard>

      <Card>
        <CardHeader
          title="لیست کلیدها"
          subtitle="فیلتر بر اساس کاربر"
          action={
            <Select
              className="!w-44 !py-2 !text-sm"
              value={filterUserId}
              onChange={(e) => setFilterUserId(e.target.value)}
            >
              <option value="">همه کاربران</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.username}
                </option>
              ))}
            </Select>
          }
        />
        <CardBody className="p-0 pt-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[800px]">
          <thead className="bg-zinc-50 text-zinc-600 border-b border-zinc-100">
            <tr>
              <th className="text-right px-6 py-4 font-semibold">کاربر</th>
              <th className="text-right px-6 py-4 font-semibold">نام</th>
              <th className="text-right px-6 py-4 font-semibold">کلید API</th>
              <th className="text-right px-6 py-4 font-semibold">وضعیت</th>
              <th className="text-right px-6 py-4 font-semibold">محدودیت</th>
              <th className="text-right px-6 py-4 font-semibold">سهمیه</th>
              <th className="text-right px-6 py-4 font-semibold">تاریخ</th>
              <th className="text-right px-6 py-4 font-semibold">عملیات</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-6 py-10 text-center text-zinc-400">
                  در حال بارگذاری…
                </td>
              </tr>
            ) : keys.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-10 text-center text-zinc-400">
                  کلیدی یافت نشد
                </td>
              </tr>
            ) : (
              keys.map((k) => (
                <tr key={k.id} className="border-t border-zinc-50 hover:bg-violet-50/30">
                  <td className="px-6 py-4 font-medium">{k.username}</td>
                  <td className="px-6 py-4">{k.name || "—"}</td>
                  <td className="px-6 py-4 max-w-xs">
                    {k.raw_key ? (
                      <div className="flex items-start gap-2">
                        <code className="text-xs break-all font-mono text-zinc-700 leading-relaxed">
                          {k.raw_key}
                        </code>
                        <button
                          type="button"
                          onClick={() => copyKey(k.raw_key!)}
                          className="text-xs text-violet-600 hover:underline shrink-0 font-medium"
                        >
                          کپی
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-zinc-400">
                        {k.key_hint || "—"} (قدیمی)
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium ${
                        k.is_active
                          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/60"
                          : "bg-zinc-100 text-zinc-600"
                      }`}
                    >
                      {k.is_active ? "فعال" : "لغو شده"}
                    </span>
                  </td>
                  <td className="px-6 py-4 tabular-nums">{k.rate_limit_per_minute}</td>
                  <td className="px-6 py-4 tabular-nums">
                    {k.monthly_token_quota.toLocaleString("fa-IR")}
                  </td>
                  <td className="px-6 py-4 text-zinc-600">
                    {new Date(k.created_at).toLocaleDateString("fa-IR")}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-3">
                      {k.is_active && (
                        <>
                          <button
                            type="button"
                            onClick={() => openEdit(k)}
                            className="text-violet-600 hover:underline text-sm font-medium"
                          >
                            ویرایش
                          </button>
                          <button
                            type="button"
                            onClick={() => revokeKey(k)}
                            className="text-rose-600 hover:underline text-sm font-medium"
                          >
                            لغو
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
        </CardBody>
      </Card>
    </PageShell>
  );
}
