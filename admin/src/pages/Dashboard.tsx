import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowLeft,
  KeyRound,
  Network,
  Server,
  TriangleAlert,
  UsersRound,
} from "lucide-react";
import { api, AdminConnection, AdminLLMModel, AdminUser, UsageSummary, ApiError } from "../api/client";
import StatCard from "../components/ui/StatCard";
import PageHeader from "../components/ui/PageHeader";
import Alert from "../components/ui/Alert";
import PageShell from "../components/ui/PageShell";
import UserShareChart from "../components/charts/UserShareChart";
import { Card, CardBody, CardHeader } from "../components/ui/Card";

function fmt(n: number) {
  return n.toLocaleString("fa-IR");
}

function UsageBar({ percent }: { percent: number }) {
  const p = Math.min(100, Math.max(0, percent));
  const color = p >= 90 ? "bg-rose-500" : p >= 70 ? "bg-amber-500" : "bg-violet-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${p}%` }} />
      </div>
      <span className="text-xs text-zinc-500 w-10 tabular-nums">{p.toLocaleString("fa-IR")}٪</span>
    </div>
  );
}

const quickLinks = [
  { to: "/models", label: "زیرساخت مدل", desc: "Provider و مدل جدید", icon: Network },
  { to: "/api-keys", label: "دسترسی‌ها", desc: "کلید، سهمیه و محدودیت", icon: KeyRound },
  { to: "/usage", label: "تحلیل مصرف", desc: "توکن و هشدار سهمیه", icon: Activity },
];

export default function Dashboard() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [usage, setUsage] = useState<UsageSummary[]>([]);
  const [connections, setConnections] = useState<AdminConnection[]>([]);
  const [models, setModels] = useState<AdminLLMModel[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        const [u, us, conns, modelList] = await Promise.all([
          api.listUsers(),
          api.listUsage(),
          api.listConnections(),
          api.listAdminModels(),
        ]);
        setUsers(u);
        setUsage(us);
        setConnections(conns);
        setModels(modelList);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "خطا در بارگذاری");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const stats = useMemo(() => {
    const activeUsers = users.filter((u) => u.is_active).length;
    const totalTokens = usage.reduce((s, r) => s + r.tokens_used, 0);
    const nearLimit = usage.filter((r) => r.percent_used >= 80).length;
    const activeConnections = connections.filter((c) => c.is_active).length;
    const activeModels = models.filter((m) => m.is_active).length;
    return { activeUsers, totalUsers: users.length, totalTokens, nearLimit, activeConnections, activeModels };
  }, [users, usage, connections, models]);

  const pieData = useMemo(() => {
    const byUser = new Map<string, number>();
    for (const r of usage) {
      if (r.tokens_used <= 0) continue;
      byUser.set(r.username, (byUser.get(r.username) || 0) + r.tokens_used);
    }
    return [...byUser.entries()]
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [usage]);

  const topConsumers = useMemo(
    () => [...usage].sort((a, b) => b.tokens_used - a.tokens_used).slice(0, 5),
    [usage],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh] text-zinc-400">
        در حال بارگذاری داشبورد…
      </div>
    );
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow="Control plane"
        title="نمای کلی Gateway"
        subtitle="سلامت زیرساخت مدل، دسترسی‌ها و مصرف را از یک نقطه پایش کنید."
        action={
          <Link
            to="/models"
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-slate-950 px-4 text-xs font-bold text-white transition-colors hover:bg-slate-800"
          >
            افزودن مدل
            <ArrowLeft size={15} />
          </Link>
        }
      />
      <Alert message={error} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="مدل‌های فعال" value={fmt(stats.activeModels)} hint={`${fmt(stats.activeConnections)} ارائه‌دهنده فعال`} tone="violet" icon={<Server size={19} />} />
        <StatCard label="کاربران فعال" value={`${fmt(stats.activeUsers)} / ${fmt(stats.totalUsers)}`} hint="کاربران دارای دسترسی" tone="zinc" icon={<UsersRound size={19} />} />
        <StatCard label="مصرف توکن" value={fmt(stats.totalTokens)} hint="جمع ماه جاری" tone="emerald" icon={<Activity size={19} />} />
        <StatCard label="نیاز به توجه" value={fmt(stats.nearLimit)} hint="کلید بالای ۸۰٪ سهمیه" tone="amber" icon={<TriangleAlert size={19} />} />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {quickLinks.map((q) => {
          const Icon = q.icon;
          return (
          <Link
            key={q.to}
            to={q.to}
            className="group flex items-center gap-4 rounded-2xl border border-slate-200/80 bg-white p-5 transition-all hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-lg hover:shadow-indigo-100/40"
          >
            <span className="flex size-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 transition-colors group-hover:bg-indigo-600 group-hover:text-white">
              <Icon size={19} />
            </span>
            <div>
              <p className="font-bold text-zinc-900">{q.label}</p>
              <p className="text-sm text-zinc-500 mt-0.5">{q.desc}</p>
            </div>
          </Link>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="سهم کاربران" subtitle="توزیع مصرف ماهانه" />
          <CardBody>
            <UserShareChart data={pieData} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="کاربران" subtitle="وضعیت حساب‌ها" />
          <CardBody className="p-0">
            {users.length === 0 ? (
              <p className="px-6 py-10 text-center text-zinc-400 text-sm">کاربری ثبت نشده</p>
            ) : (
              <ul className="divide-y divide-zinc-50 max-h-[320px] overflow-y-auto">
                {users.map((u) => (
                  <li key={u.id} className="flex items-center justify-between gap-4 px-6 py-4 hover:bg-zinc-50/80">
                    <div>
                      <p className="font-semibold text-zinc-900">{u.username}</p>
                      <p className="text-xs text-zinc-400 mt-0.5">{u.email || "بدون ایمیل"}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-sm text-zinc-500 tabular-nums">{u.key_count} کلید</span>
                      <span className={`text-xs font-bold px-2 py-1 rounded ${u.is_active ? "bg-emerald-50 text-emerald-700" : "bg-zinc-100 text-zinc-500"}`}>
                        {u.is_active ? "فعال" : "غیرفعال"}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="پرمصرف‌ترین کلیدها"
          subtitle="۵ کلید برتر — گزارش کامل در مصرف توکن"
          action={
            <Link to="/usage" className="text-sm font-semibold text-violet-600 hover:text-violet-800">
              مشاهده همه ←
            </Link>
          }
        />
        <CardBody className="overflow-x-auto p-0">
          <table className="admin-table min-w-[640px]">
            <thead>
              <tr>
                {["کاربر", "کلید", "مصرف", "سهمیه", "پیشرفت"].map((h) => (
                  <th key={h} className="text-right px-6 py-3 font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topConsumers.length === 0 ? (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-zinc-400">هنوز مصرفی ثبت نشده</td></tr>
              ) : topConsumers.map((r) => (
                <tr key={r.api_key_id} className="border-b border-zinc-50 hover:bg-violet-50/30">
                  <td className="px-6 py-4 font-semibold">{r.username}</td>
                  <td className="px-6 py-4 text-zinc-600">{r.key_name || "—"}</td>
                  <td className="px-6 py-4 tabular-nums font-bold">{fmt(r.tokens_used)}</td>
                  <td className="px-6 py-4 tabular-nums text-zinc-500">{fmt(r.monthly_token_quota)}</td>
                  <td className="px-6 py-4 w-48"><UsageBar percent={r.percent_used} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>
    </PageShell>
  );
}
