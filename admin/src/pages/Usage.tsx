import { useEffect, useMemo, useState } from "react";
import { Activity, Gauge, KeyRound, Timer, TriangleAlert } from "lucide-react";
import { api, UsageSummary, ModelMetricsSummary, ApiError } from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import PageShell from "../components/ui/PageShell";
import Alert from "../components/ui/Alert";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import StatCard from "../components/ui/StatCard";
import UsageKeyChart from "../components/charts/UsageKeyChart";

function fmt(n: number) {
  return n.toLocaleString("fa-IR");
}

function fmtMs(n: number) {
  if (n >= 1000) return `${(n / 1000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })}s`;
  return `${Math.round(n).toLocaleString("fa-IR")}ms`;
}

function UsageBar({ percent }: { percent: number }) {
  const p = Math.min(100, Math.max(0, percent));
  const color = p >= 90 ? "bg-rose-500" : p >= 70 ? "bg-amber-500" : "bg-violet-500";
  return (
    <div className="w-full bg-zinc-100 rounded-full h-2 overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${p}%` }} />
    </div>
  );
}

export default function Usage() {
  const [rows, setRows] = useState<UsageSummary[]>([]);
  const [metrics, setMetrics] = useState<ModelMetricsSummary | null>(null);
  const [days, setDays] = useState(7);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [usage, modelMetrics] = await Promise.all([
          api.listUsage(),
          api.listModelMetrics(days),
        ]);
        setRows(usage);
        setMetrics(modelMetrics);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "خطا");
      } finally {
        setLoading(false);
      }
    })();
  }, [days]);

  const totalUsed = useMemo(() => rows.reduce((s, r) => s + r.tokens_used, 0), [rows]);
  const totalQuota = useMemo(() => rows.reduce((s, r) => s + r.monthly_token_quota, 0), [rows]);
  const totals = metrics?.totals;

  const keyChartItems = useMemo(
    () =>
      [...rows]
        .sort((a, b) => b.tokens_used - a.tokens_used)
        .map((r) => ({
          id: r.api_key_id,
          title: r.key_name || `کلید ${r.username}`,
          subtitle: `کاربر: ${r.username}`,
          used: r.tokens_used,
          quota: r.monthly_token_quota,
          percent: r.percent_used,
        })),
    [rows],
  );

  const alerts = useMemo(
    () => [...rows].filter((r) => r.percent_used >= 70).sort((a, b) => b.percent_used - a.percent_used),
    [rows],
  );

  return (
    <PageShell>
      <PageHeader
        eyebrow="Observability"
        title="مصرف و متریک‌ها"
        subtitle="سهمیه کلیدها به‌همراه latency، خطا و توکن به‌ازای هر مدل."
      />
      <Alert message={error} onClose={() => setError("")} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">
          متریک مدل‌ها {metrics ? `از ${metrics.from_date} تا ${metrics.to_date}` : "—"}
        </p>
        <select
          className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={1}>۲۴ ساعت</option>
          <option value={7}>۷ روز</option>
          <option value={14}>۱۴ روز</option>
          <option value={30}>۳۰ روز</option>
        </select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="درخواست مدل" value={fmt(totals?.requests || 0)} hint={`بازه ${days} روزه`} tone="violet" icon={<Activity size={19} />} />
        <StatCard label="میانگین Latency" value={fmtMs(totals?.avg_latency_ms || 0)} hint="زمان پاسخ gateway→upstream" tone="zinc" icon={<Timer size={19} />} />
        <StatCard label="نرخ خطا" value={`${(totals?.error_rate || 0).toLocaleString("fa-IR")}٪`} hint={`${fmt(totals?.errors || 0)} خطا`} tone="amber" icon={<TriangleAlert size={19} />} />
        <StatCard label="توکن مدل‌ها" value={fmt(totals?.total_tokens || 0)} hint={`Fallback: ${fmt(totals?.fallbacks || 0)}`} tone="emerald" icon={<Gauge size={19} />} />
      </div>

      <Card>
        <CardHeader title="متریک به‌ازای مدل" subtitle="درخواست، latency، خطا و مصرف توکن" />
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="admin-table min-w-[900px]">
              <thead>
                <tr>
                  {["مدل", "درخواست", "خطا", "نرخ خطا", "Fallback", "میانگین Latency", "Prompt", "Completion", "کل توکن"].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9} className="px-6 py-12 text-center text-zinc-400">بارگذاری…</td></tr>
                ) : !metrics?.models.length ? (
                  <tr><td colSpan={9} className="px-6 py-12 text-center text-zinc-400">هنوز ترافیکی ثبت نشده — یک چت بزنید</td></tr>
                ) : metrics.models.map((m) => (
                  <tr key={m.model_id}>
                    <td className="font-mono text-xs font-bold text-slate-900" dir="ltr">{m.model_id}</td>
                    <td className="tabular-nums font-bold">{fmt(m.requests)}</td>
                    <td className="tabular-nums text-rose-600">{fmt(m.errors)}</td>
                    <td className="tabular-nums">{m.error_rate.toLocaleString("fa-IR")}٪</td>
                    <td className="tabular-nums">{fmt(m.fallbacks)}</td>
                    <td className="tabular-nums font-semibold">{fmtMs(m.avg_latency_ms)}</td>
                    <td className="tabular-nums text-slate-500">{fmt(m.prompt_tokens)}</td>
                    <td className="tabular-nums text-slate-500">{fmt(m.completion_tokens)}</td>
                    <td className="tabular-nums font-bold">{fmt(m.total_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="جمع مصرف کلیدها" value={fmt(totalUsed)} hint="توکن در ماه جاری" tone="violet" icon={<Activity size={19} />} />
        <StatCard label="جمع سهمیه" value={fmt(totalQuota)} hint="سقف تخصیص‌یافته" tone="zinc" icon={<Gauge size={19} />} />
        <StatCard label="کلید مصرف‌کننده" value={rows.filter((r) => r.tokens_used > 0).length} hint="دارای ترافیک این ماه" tone="emerald" icon={<KeyRound size={19} />} />
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader
            title="مصرف به تفکیک کلید"
            subtitle={`${keyChartItems.length.toLocaleString("fa-IR")} کلید — اسکرول برای بیشتر`}
          />
          <CardBody>
            <UsageKeyChart items={keyChartItems} maxHeight={420} />
          </CardBody>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader title="نیاز به توجه" subtitle="کلیدهای نزدیک به سقف سهمیه" />
          <CardBody className="p-0">
            {loading ? (
              <p className="px-6 py-10 text-center text-zinc-400 text-sm">بارگذاری…</p>
            ) : alerts.length === 0 ? (
              <p className="px-6 py-10 text-center text-zinc-400 text-sm">همه کلیدها در وضعیت عادی هستند</p>
            ) : (
              <ul className="divide-y divide-zinc-50 max-h-[420px] overflow-y-auto">
                {alerts.map((r) => (
                  <li key={r.api_key_id} className="flex items-center justify-between gap-4 px-6 py-4 hover:bg-amber-50/40">
                    <div className="min-w-0">
                      <p className="font-semibold text-zinc-900 truncate">{r.key_name || "بدون نام"}</p>
                      <p className="text-xs text-zinc-400 mt-0.5">{r.username}</p>
                    </div>
                    <div className="text-left shrink-0">
                      <span className={`text-xs font-bold px-2 py-1 rounded ${r.percent_used >= 90 ? "bg-rose-50 text-rose-600" : "bg-amber-50 text-amber-700"}`}>
                        {r.percent_used.toLocaleString("fa-IR")}٪
                      </span>
                      <p className="text-xs text-zinc-500 mt-1 tabular-nums">{fmt(r.tokens_used)} / {fmt(r.monthly_token_quota)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="جدول تفصیلی کلیدها" />
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="admin-table min-w-[720px]">
              <thead>
                <tr>
                  {["کاربر", "کلید", "مصرف", "سهمیه", "درصد", "پیشرفت"].map((h) => (
                    <th key={h} className="text-right px-6 py-3 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="px-6 py-12 text-center text-zinc-400">بارگذاری…</td></tr>
                ) : rows.length === 0 ? (
                  <tr><td colSpan={6} className="px-6 py-12 text-center text-zinc-400">داده‌ای نیست</td></tr>
                ) : rows.map((r) => (
                  <tr key={r.api_key_id} className="border-b border-zinc-50 hover:bg-violet-50/30">
                    <td className="px-6 py-4 font-semibold">{r.username}</td>
                    <td className="px-6 py-4 text-zinc-600">{r.key_name || "—"}</td>
                    <td className="px-6 py-4 tabular-nums font-bold">{fmt(r.tokens_used)}</td>
                    <td className="px-6 py-4 tabular-nums text-zinc-500">{fmt(r.monthly_token_quota)}</td>
                    <td className="px-6 py-4">
                      <span className={`text-xs font-bold px-2 py-1 rounded ${r.percent_used >= 90 ? "bg-rose-50 text-rose-600" : r.percent_used >= 70 ? "bg-amber-50 text-amber-700" : "bg-violet-50 text-violet-700"}`}>
                        {r.percent_used.toLocaleString("fa-IR")}٪
                      </span>
                    </td>
                    <td className="px-6 py-4 w-44"><UsageBar percent={r.percent_used} /></td>
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
