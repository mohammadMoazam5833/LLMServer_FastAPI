import { FormEvent, useEffect, useState } from "react";
import {
  Box,
  CheckCircle2,
  FlaskConical,
  Network,
  Plus,
  Power,
  RefreshCw,
  Server,
  Trash2,
} from "lucide-react";
import {
  api,
  AdminConnection,
  AdminLLMModel,
  AdminConnectionTestResult,
  ApiError,
} from "../api/client";
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
  Select,
  PrimaryButton,
  GhostButton,
} from "../components/ui/Form";

const PROVIDERS = [
  { value: "vllm", label: "vLLM", hint: "http://HOST:8003/v1" },
  { value: "ollama", label: "Ollama", hint: "http://HOST:11434 یا .../v1" },
  { value: "openai", label: "OpenAI-compatible", hint: "هر api_base شبیه OpenAI" },
] as const;

export default function Models() {
  const [connections, setConnections] = useState<AdminConnection[]>([]);
  const [models, setModels] = useState<AdminLLMModel[]>([]);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(true);

  const [connId, setConnId] = useState("local-vllm");
  const [connName, setConnName] = useState("Local vLLM");
  const [connProvider, setConnProvider] = useState<string>("vllm");
  const [connUrl, setConnUrl] = useState("http://127.0.0.1:8003/v1");
  const [connKey, setConnKey] = useState("");
  const [creatingConn, setCreatingConn] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AdminConnectionTestResult | null>(null);

  const [modelId, setModelId] = useState("");
  const [modelPath, setModelPath] = useState("");
  const [modelConnId, setModelConnId] = useState("");
  const [modelFallbacks, setModelFallbacks] = useState("");
  const [creatingModel, setCreatingModel] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [c, m] = await Promise.all([api.listConnections(), api.listAdminModels()]);
      setConnections(c);
      setModels(m);
      if (!modelConnId && c.length) {
        const active = c.find((x) => x.is_active) || c[0];
        setModelConnId(active.id);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در بارگذاری");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const meta = PROVIDERS.find((p) => p.value === connProvider);
    if (meta && !connUrl) setConnUrl(meta.hint.startsWith("http") ? meta.hint : "");
  }, [connProvider]);

  async function handleTestDraft() {
    setTesting(true);
    setError("");
    setTestResult(null);
    try {
      const res = await api.testConnectionDraft({
        base_url: connUrl,
        api_key: connKey || undefined,
        provider_type: connProvider,
      });
      setTestResult(res);
      if (!res.ok) setError(res.error || "اتصال ناموفق");
      else setInfo(`تست موفق — upstream models: ${(res.model_ids || []).join(", ") || "(خالی)"}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در تست");
    } finally {
      setTesting(false);
    }
  }

  async function handleCreateConnection(e: FormEvent) {
    e.preventDefault();
    setCreatingConn(true);
    setError("");
    setInfo("");
    try {
      await api.createConnection({
        id: connId,
        name: connName,
        base_url: connUrl,
        provider_type: connProvider,
        api_key: connKey || undefined,
      });
      setInfo("Credential / اتصال ذخیره شد");
      setConnKey("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در ساخت اتصال");
    } finally {
      setCreatingConn(false);
    }
  }

  async function handleCreateModel(e: FormEvent) {
    e.preventDefault();
    setCreatingModel(true);
    setError("");
    setInfo("");
    try {
      const fallback_model_ids = modelFallbacks
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      await api.createAdminModel({
        id: modelId,
        model_path: modelPath,
        connection_id: modelConnId,
        fallback_model_ids,
      });
      setInfo("model_name ثبت شد (مثل LiteLLM model_list)");
      setModelId("");
      setModelPath("");
      setModelFallbacks("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در ساخت مدل");
    } finally {
      setCreatingModel(false);
    }
  }

  async function editFallbacks(m: AdminLLMModel) {
    const current = (m.fallback_model_ids || []).join(", ");
    const next = window.prompt(
      `Fallback برای «${m.id}» (شناسه مدل‌ها با کاما، خالی = بدون fallback):`,
      current,
    );
    if (next === null) return;
    setError("");
    setInfo("");
    try {
      const fallback_model_ids = next
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      await api.updateAdminModel(m.id, { fallback_model_ids });
      setInfo(`Fallback مدل «${m.id}» به‌روز شد`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در تنظیم Fallback");
    }
  }

  async function toggleConnection(c: AdminConnection) {
    try {
      await api.updateConnection(c.id, { is_active: !c.is_active });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا");
    }
  }

  async function deleteConnection(c: AdminConnection) {
    if (
      !confirm(
        `اتصال «${c.id}» حذف شود؟\nمدل‌های وابسته غیرفعال و unbound می‌شوند (مثل LiteLLM).`,
      )
    ) {
      return;
    }
    setError("");
    setInfo("");
    try {
      await api.deleteConnection(c.id);
      setInfo(`اتصال ${c.id} حذف شد — مدل‌های وابسته قطع شدند`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در حذف اتصال");
    }
  }

  async function testSaved(c: AdminConnection) {
    setTesting(true);
    setError("");
    setInfo("");
    try {
      const res = await api.testSavedConnection(c.id);
      setTestResult(res);
      if (res.ok) setInfo(`تست ${c.id} موفق — ${(res.model_ids || []).join(", ")}`);
      else setError(res.error || "ناموفق");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در تست");
    } finally {
      setTesting(false);
    }
  }

  async function toggleModel(m: AdminLLMModel) {
    try {
      await api.updateAdminModel(m.id, { is_active: !m.is_active });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا");
    }
  }

  async function deleteModel(m: AdminLLMModel) {
    if (!confirm(`مدل «${m.id}» حذف شود؟`)) return;
    setError("");
    setInfo("");
    try {
      await api.deleteAdminModel(m.id);
      setInfo(`مدل ${m.id} حذف شد`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در حذف مدل");
    }
  }

  function applyTestModelIds() {
    if (!testResult?.model_ids?.length) return;
    const first = testResult.model_ids[0];
    if (!modelPath) setModelPath(first);
    if (!modelId) setModelId(first.replace(/[^a-zA-Z0-9._-]/g, "-").slice(0, 64));
  }

  const providerHint = PROVIDERS.find((p) => p.value === connProvider)?.hint || "";
  const activeConns = connections.filter((c) => c.is_active).length;
  const activeModels = models.filter((m) => m.is_active).length;

  return (
    <PageShell>
      <PageHeader
        eyebrow="Model infrastructure"
        title="ارائه‌دهندگان و مدل‌ها"
        subtitle="اتصال به زیرساخت inference و انتشار مدل‌ها روی API یکپارچه Gateway."
        action={
          <div className="flex items-center gap-2">
            <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
              <strong className="ml-1 text-slate-950">{activeConns}</strong> اتصال فعال
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
              <strong className="ml-1 text-slate-950">{activeModels}</strong> مدل فعال
            </div>
          </div>
        }
      />
      <Alert message={error} onClose={() => setError("")} />
      {info && (
        <div className="mb-5 flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm text-emerald-800">
          <CheckCircle2 size={17} />
          {info}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { n: "۱", icon: Network, title: "اتصال Provider", text: "نوع سرویس و api_base را تعریف کنید." },
          { n: "۲", icon: FlaskConical, title: "تست اتصال", text: "مدل‌های واقعی upstream را دریافت کنید." },
          { n: "۳", icon: Box, title: "انتشار مدل", text: "نام عمومی را به مدل upstream متصل کنید." },
        ].map(({ n, icon: Icon, title, text }) => (
          <div key={n} className="flex items-start gap-3 rounded-2xl border border-slate-200/80 bg-white p-4">
            <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-950 text-xs font-black text-white">{n}</div>
            <div>
              <p className="flex items-center gap-1.5 text-xs font-extrabold text-slate-800"><Icon size={14} className="text-indigo-500" />{title}</p>
              <p className="mt-1 text-[11px] leading-5 text-slate-400">{text}</p>
            </div>
          </div>
        ))}
      </div>

      <FormCard
        title="اتصال Provider جدید"
        subtitle="مشخصات endpoint سازگار با OpenAI را وارد کنید؛ کلید دسترسی به‌شکل رمز‌شده نگهداری می‌شود."
      >
        <form onSubmit={handleCreateConnection} className="space-y-4">
          <FormRow>
            <FormCol span={3}>
              <FormField label="شناسه داخلی" hint="یکتا، بدون فاصله">
                <Input value={connId} onChange={(e) => setConnId(e.target.value)} required placeholder="local-vllm" dir="ltr" />
              </FormField>
            </FormCol>
            <FormCol span={3}>
              <FormField label="نام نمایشی">
                <Input value={connName} onChange={(e) => setConnName(e.target.value)} required />
              </FormField>
            </FormCol>
            <FormCol span={2}>
              <FormField label="نوع Provider">
                <Select value={connProvider} onChange={(e) => setConnProvider(e.target.value)}>
                  {PROVIDERS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </Select>
              </FormField>
            </FormCol>
            <FormCol span={4}>
              <FormField label="API Base URL" hint={providerHint}>
                <Input
                  value={connUrl}
                  onChange={(e) => setConnUrl(e.target.value)}
                  required
                  placeholder={providerHint}
                  dir="ltr"
                />
              </FormField>
            </FormCol>
          </FormRow>
          <FormRow>
            <FormCol span={6}>
              <FormField label="API Key" hint="برای vLLM/Ollama محلی معمولاً خالی">
                <Input
                  type="password"
                  value={connKey}
                  onChange={(e) => setConnKey(e.target.value)}
                  placeholder="اختیاری"
                  dir="ltr"
                />
              </FormField>
            </FormCol>
            <FormSubmitCol span={6}>
              <div className="flex w-full flex-wrap items-center justify-end gap-2">
                <GhostButton type="button" onClick={handleTestDraft} disabled={testing} className="h-11 border border-slate-200 px-4">
                  <RefreshCw size={14} className={testing ? "animate-spin" : ""} />
                  {testing ? "در حال تست" : "تست اتصال"}
                </GhostButton>
                <PrimaryButton type="submit" disabled={creatingConn}>
                  <Plus size={15} />
                  {creatingConn ? "در حال ذخیره" : "ذخیره Provider"}
                </PrimaryButton>
              </div>
            </FormSubmitCol>
          </FormRow>
        </form>
      </FormCard>

      <Card className="mb-6">
        <CardHeader title="Providerهای متصل" subtitle="endpointهای inference قابل استفاده توسط Gateway" />
        <CardBody className="p-0">
          {loading ? (
            <p className="px-6 py-12 text-center text-sm text-slate-400">در حال بارگذاری…</p>
          ) : connections.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <Server className="mx-auto text-slate-300" size={30} />
              <p className="mt-3 text-sm font-bold text-slate-700">هنوز Provider اضافه نشده</p>
              <p className="mt-1 text-xs text-slate-400">برای شروع یک vLLM یا Ollama متصل کنید.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="admin-table min-w-[760px]">
                <thead>
                  <tr>
                    <th>شناسه</th>
                    <th>نوع</th>
                    <th>API Base</th>
                    <th>وضعیت</th>
                    <th>عملیات</th>
                  </tr>
                </thead>
                <tbody>
                  {connections.map((c) => (
                    <tr key={c.id}>
                      <td className="font-mono text-xs font-bold text-slate-800" dir="ltr">{c.id}</td>
                      <td><span className="rounded-lg bg-indigo-50 px-2.5 py-1 font-mono text-[11px] font-bold text-indigo-700">{c.provider_type}</span></td>
                      <td className="max-w-[280px] truncate font-mono text-xs text-slate-500" dir="ltr" title={c.base_url}>
                        {c.base_url}
                      </td>
                      <td>
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${c.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                          <span className={`size-1.5 rounded-full ${c.is_active ? "bg-emerald-500" : "bg-slate-400"}`} />
                          {c.is_active ? "فعال" : "غیرفعال"}
                        </span>
                      </td>
                      <td className="space-x-1 space-x-reverse whitespace-nowrap">
                        <GhostButton type="button" onClick={() => testSaved(c)} disabled={testing}><FlaskConical size={13} />تست</GhostButton>
                        <GhostButton type="button" onClick={() => toggleConnection(c)}>
                          <Power size={13} />{c.is_active ? "غیرفعال" : "فعال"}
                        </GhostButton>
                        <GhostButton type="button" onClick={() => deleteConnection(c)} className="text-rose-600 hover:border-rose-100 hover:bg-rose-50 hover:text-rose-700"><Trash2 size={13} />حذف</GhostButton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <FormCard
        title="انتشار مدل روی Gateway"
        subtitle="یک نام عمومی برای کلاینت‌ها تعریف و آن را به شناسه دقیق مدل upstream متصل کنید."
      >
        <form onSubmit={handleCreateModel} className="space-y-4">
          <FormRow>
            <FormCol span={3}>
              <FormField label="نام عمومی مدل" hint="برای کلاینت‌ها">
                <Input value={modelId} onChange={(e) => setModelId(e.target.value)} required placeholder="qwen3-coder-30b" dir="ltr" />
              </FormField>
            </FormCol>
            <FormCol span={3}>
              <FormField label="شناسه Upstream" hint="عین خروجی /models">
                <Input value={modelPath} onChange={(e) => setModelPath(e.target.value)} required placeholder="qwen3-coder-30b" dir="ltr" />
              </FormField>
            </FormCol>
            <FormCol span={3}>
              <FormField label="Provider متصل">
                <Select value={modelConnId} onChange={(e) => setModelConnId(e.target.value)} required>
                  <option value="">انتخاب اتصال</option>
                  {connections.filter((c) => c.is_active).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.provider_type}:{c.id}
                    </option>
                  ))}
                </Select>
              </FormField>
            </FormCol>
            <FormCol span={3}>
              <FormField label="Fallback" hint="شناسه مدل‌های پشتیبان، با کاما">
                <Input
                  value={modelFallbacks}
                  onChange={(e) => setModelFallbacks(e.target.value)}
                  placeholder="backup-model-id"
                  dir="ltr"
                />
              </FormField>
            </FormCol>
          </FormRow>
          <FormRow>
            <FormSubmitCol span={12}>
              <div className="flex w-full flex-wrap items-center justify-end gap-2">
                {testResult?.ok && (
                  <GhostButton type="button" onClick={applyTestModelIds} className="h-11 border border-slate-200 px-3">
                    <CheckCircle2 size={13} />از تست
                  </GhostButton>
                )}
                <PrimaryButton type="submit" disabled={creatingModel || !modelConnId}>
                  <Plus size={15} />
                  {creatingModel ? "در حال انتشار" : "انتشار مدل"}
                </PrimaryButton>
              </div>
            </FormSubmitCol>
          </FormRow>
        </form>
      </FormCard>

      <Card>
        <CardHeader title="کاتالوگ مدل‌ها" subtitle="مدل‌های منتشرشده روی API یکپارچه Gateway" />
        <CardBody className="p-0">
          {models.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <Box className="mx-auto text-slate-300" size={30} />
              <p className="mt-3 text-sm font-bold text-slate-700">مدلی منتشر نشده</p>
              <p className="mt-1 text-xs text-slate-400">پس از اتصال Provider، اولین مدل را منتشر کنید.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="admin-table min-w-[1080px]">
                <thead>
                  <tr>
                    <th>نام عمومی</th>
                    <th>شناسه Upstream</th>
                    <th>نوع</th>
                    <th>Provider</th>
                    <th>API Base</th>
                    <th>Fallback</th>
                    <th>وضعیت</th>
                    <th>عملیات</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <tr key={m.id}>
                      <td className="font-mono text-xs font-bold text-slate-900" dir="ltr">{m.id}</td>
                      <td className="font-mono text-xs text-slate-500" dir="ltr">{m.model_path}</td>
                      <td><span className="rounded-lg bg-slate-100 px-2 py-1 font-mono text-[11px] font-bold text-slate-600">{m.provider}</span></td>
                      <td className="font-mono text-xs text-slate-500" dir="ltr">{m.connection_id || "—"}</td>
                      <td className="max-w-[210px] truncate font-mono text-xs text-slate-400" dir="ltr" title={m.effective_base_url}>
                        {m.effective_base_url || "—"}
                      </td>
                      <td className="max-w-[160px] truncate font-mono text-xs text-slate-500" dir="ltr" title={(m.fallback_model_ids || []).join(", ")}>
                        {(m.fallback_model_ids || []).length ? m.fallback_model_ids.join(", ") : "—"}
                      </td>
                      <td>
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${m.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                          <span className={`size-1.5 rounded-full ${m.is_active ? "bg-emerald-500" : "bg-slate-400"}`} />
                          {m.is_active ? "فعال" : "غیرفعال"}
                        </span>
                      </td>
                      <td className="space-x-1 space-x-reverse whitespace-nowrap">
                        <GhostButton type="button" onClick={() => editFallbacks(m)}>
                          <RefreshCw size={13} />Fallback
                        </GhostButton>
                        <GhostButton type="button" onClick={() => toggleModel(m)}>
                          <Power size={13} />{m.is_active ? "غیرفعال" : "فعال"}
                        </GhostButton>
                        <GhostButton type="button" onClick={() => deleteModel(m)} className="text-rose-600 hover:border-rose-100 hover:bg-rose-50 hover:text-rose-700"><Trash2 size={13} />حذف</GhostButton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </PageShell>
  );
}
