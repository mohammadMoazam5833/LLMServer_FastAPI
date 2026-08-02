import { FormEvent, useEffect, useState } from "react";
import { Plus, Power, UserRound } from "lucide-react";
import { api, AdminUser, ApiError } from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import PageShell from "../components/ui/PageShell";
import Alert from "../components/ui/Alert";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import {
  FormCard,
  FormField,
  FormRow,
  FormCol,
  FormSubmitCol,
  Input,
  PrimaryButton,
} from "../components/ui/Form";

export default function Users() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در بارگذاری");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      await api.createUser({ username, password, email });
      setUsername(""); setPassword(""); setEmail("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در ساخت کاربر");
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(user: AdminUser) {
    setError("");
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا");
    }
  }

  const activeCount = users.filter((u) => u.is_active).length;

  return (
    <PageShell>
      <PageHeader
        eyebrow="Identity & access"
        title="کاربران"
        subtitle="حساب‌های انسانی دارای دسترسی به Gateway را مدیریت کنید."
        action={
          <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
            <strong className="ml-1 text-slate-950">{activeCount}</strong> از {users.length} فعال
          </div>
        }
      />
      <Alert message={error} onClose={() => setError("")} />

      <FormCard title="کاربر جدید" subtitle="پس از ساخت حساب می‌توانید کلید و سهمیه دسترسی تعریف کنید.">
        <form onSubmit={handleCreate}>
          <FormRow>
            <FormCol span={3}>
              <FormField label="نام کاربری">
                <Input placeholder="user_1" value={username} onChange={(e) => setUsername(e.target.value)} required />
              </FormField>
            </FormCol>
            <FormCol span={3}>
              <FormField label="رمز عبور">
                <Input type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </FormField>
            </FormCol>
            <FormCol span={3}>
              <FormField label="ایمیل (اختیاری)">
                <Input type="email" placeholder="user@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              </FormField>
            </FormCol>
            <FormSubmitCol span={3}>
              <PrimaryButton type="submit" disabled={creating} className="w-full">
                <Plus size={15} />
                {creating ? "در حال ساخت…" : "ساخت کاربر"}
              </PrimaryButton>
            </FormSubmitCol>
          </FormRow>
        </form>
      </FormCard>

      <Card>
        <CardHeader title="فهرست کاربران" subtitle="وضعیت حساب و تعداد کلیدهای هر کاربر" />
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="admin-table min-w-[720px]">
              <thead>
                <tr>
                  {["شناسه", "نام کاربری", "ایمیل", "وضعیت", "کلیدها", "عملیات"].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="px-6 py-12 text-center text-zinc-400">در حال بارگذاری…</td></tr>
                ) : users.length === 0 ? (
                  <tr><td colSpan={6} className="px-6 py-12 text-center text-zinc-400">کاربری یافت نشد</td></tr>
                ) : users.map((u) => (
                  <tr key={u.id}>
                    <td className="text-slate-400 tabular-nums">{u.id}</td>
                    <td>
                      <div className="flex items-center gap-2.5">
                        <span className="grid size-8 place-items-center rounded-lg bg-indigo-50 text-indigo-600"><UserRound size={14} /></span>
                        <span className="font-bold text-slate-800">{u.username}</span>
                      </div>
                    </td>
                    <td className="text-slate-500">{u.email || "—"}</td>
                    <td>
                      <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${u.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                        <span className={`size-1.5 rounded-full ${u.is_active ? "bg-emerald-500" : "bg-slate-400"}`} />
                        {u.is_active ? "فعال" : "غیرفعال"}
                      </span>
                    </td>
                    <td className="font-bold tabular-nums">{u.key_count}</td>
                    <td>
                      <button type="button" onClick={() => toggleActive(u)} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100">
                        <Power size={13} />{u.is_active ? "غیرفعال" : "فعال"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </PageShell>
  );
}
