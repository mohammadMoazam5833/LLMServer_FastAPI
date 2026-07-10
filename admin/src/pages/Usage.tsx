import { useEffect, useMemo, useState } from "react";
import { api, UsageSummary, ApiError } from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import PageShell from "../components/ui/PageShell";
import Alert from "../components/ui/Alert";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import StatCard from "../components/ui/StatCard";
import UsageKeyChart from "../components/charts/UsageKeyChart";

function fmt(n: number) {
  return n.toLocaleString("fa-IR");
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
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        setRows(await api.listUsage());
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "خطا");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const totalUsed = useMemo(() => rows.reduce((s, r) => s + r.tokens_used, 0), [rows]);
  const totalQuota = useMemo(() => rows.reduce((s, r) => s + r.monthly_token_quota, 0), [rows]);

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
      <PageHeader title="مصرف توکن" subtitle="گزارش ماه جاری" />
      <Alert message={error} />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="جمع مصرف" value={fmt(totalUsed)} hint="توکن" tone="violet" icon="⚡" />
        <StatCard label="جمع سهمیه" value={fmt(totalQuota)} hint="سقف کل" tone="zinc" icon="◎" />
        <StatCard label="کلید فعال" value={rows.filter((r) => r.tokens_used > 0).length} hint="با مصرف" tone="emerald" icon="▤" />
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
        <CardHeader title="جدول تفصیلی" />
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 border-b border-zinc-100 text-zinc-500 text-xs uppercase tracking-wide">
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
