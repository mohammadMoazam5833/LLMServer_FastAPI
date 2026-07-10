import { FormEvent, useEffect, useState } from "react";
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
        title="کاربران"
        subtitle={`${activeCount} فعال از ${users.length} کاربر`}
      />
      <Alert message={error} />

      <FormCard title="ساخت کاربر جدید" subtitle="اطلاعات کاربر را وارد کنید و ذخیره کنید">
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
                {creating ? "در حال ساخت…" : "+ ساخت کاربر"}
              </PrimaryButton>
            </FormSubmitCol>
          </FormRow>
        </form>
      </FormCard>

      <Card>
        <CardHeader title="لیست کاربران" subtitle="مدیریت وضعیت دسترسی" />
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-zinc-600 border-b border-zinc-100">
                <tr>
                  {["شناسه", "نام کاربری", "ایمیل", "وضعیت", "کلیدها", "عملیات"].map((h) => (
                    <th key={h} className="text-right px-6 py-4 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="px-6 py-12 text-center text-zinc-400">در حال بارگذاری…</td></tr>
                ) : users.length === 0 ? (
                  <tr><td colSpan={6} className="px-6 py-12 text-center text-zinc-400">کاربری یافت نشد</td></tr>
                ) : users.map((u) => (
                  <tr key={u.id} className="border-b border-zinc-50 hover:bg-zinc-50/80">
                    <td className="px-6 py-4 text-zinc-400 tabular-nums">{u.id}</td>
                    <td className="px-6 py-4 font-bold text-zinc-800">{u.username}</td>
                    <td className="px-6 py-4 text-zinc-600">{u.email || "—"}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex px-2.5 py-1 rounded-md text-xs font-bold ${u.is_active ? "bg-emerald-50 text-emerald-700" : "bg-zinc-100 text-zinc-500"}`}>
                        {u.is_active ? "فعال" : "غیرفعال"}
                      </span>
                    </td>
                    <td className="px-6 py-4 tabular-nums">{u.key_count}</td>
                    <td className="px-6 py-4">
                      <button type="button" onClick={() => toggleActive(u)} className="text-violet-600 hover:text-violet-800 text-sm font-semibold">
                        {u.is_active ? "غیرفعال" : "فعال"}
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
