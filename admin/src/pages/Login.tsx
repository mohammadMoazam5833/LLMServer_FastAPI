import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, KeyRound, Network, ShieldCheck } from "lucide-react";
import { api, ApiError, setToken } from "../api/client";
import BrandLogo from "../components/BrandLogo";

const inputClass =
  "w-full h-12 bg-white border border-slate-200 rounded-xl px-4 text-sm shadow-sm shadow-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      setToken((await api.login(username, password)).access_token);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطا در ورود");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <div className="relative hidden flex-1 overflow-hidden bg-[#0b1120] p-16 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute -left-32 -top-32 size-[480px] rounded-full bg-indigo-600/20 blur-3xl" />
        <div className="absolute -bottom-44 right-24 size-[420px] rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative"><BrandLogo size="lg" /></div>
        <div className="relative max-w-xl">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-indigo-200">
            <ShieldCheck size={14} />
            کنترل‌پلین امن زیرساخت هوش مصنوعی
          </div>
          <h1 className="text-5xl font-black leading-[1.2] tracking-[-0.04em] xl:text-6xl">
            تمام مدل‌ها،
            <br />
            <span className="text-indigo-400">یک درگاه هوشمند.</span>
          </h1>
          <p className="mt-6 max-w-md text-base leading-8 text-slate-400">
            مدیریت ارائه‌دهندگان، مدل‌ها، دسترسی‌ها و هزینه‌ها در یک تجربه عملیاتی یکپارچه.
          </p>
          <div className="mt-9 flex gap-3">
            {[
              { icon: Network, text: "چند ارائه‌دهنده" },
              { icon: KeyRound, text: "کنترل دسترسی" },
            ].map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs text-slate-300">
                <Icon size={14} className="text-indigo-400" />
                {text}
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs font-medium tracking-wider text-slate-700">LLM GATEWAY CONTROL PLANE</p>
      </div>

      <div className="flex flex-1 items-center justify-center p-6 sm:p-10">
        <form onSubmit={handleSubmit} className="w-full max-w-[400px] rounded-3xl border border-slate-200/80 bg-white p-7 shadow-2xl shadow-slate-200/50 sm:p-9">
          <div className="mb-8 inline-flex rounded-2xl bg-slate-950 p-3 lg:hidden">
            <BrandLogo size="md" />
          </div>
          <div>
            <p className="text-xs font-extrabold tracking-wider text-indigo-600">ADMIN CONSOLE</p>
            <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">خوش آمدید</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">برای مدیریت Gateway با حساب مدیر وارد شوید.</p>
          </div>
          {error && <p className="mt-6 rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
          <label className="mt-7 block space-y-2">
            <span className="text-xs font-bold text-slate-700">نام کاربری</span>
            <input
              id="admin-username"
              name="username"
              autoComplete="username"
              className={inputClass}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </label>
          <label className="mt-5 block space-y-2">
            <span className="text-xs font-bold text-slate-700">رمز عبور</span>
            <input
              id="admin-password"
              name="password"
              type="password"
              autoComplete="current-password"
              className={inputClass}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={loading} className="mt-7 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 text-sm font-bold text-white shadow-lg shadow-indigo-600/20 transition-all hover:-translate-y-px hover:bg-indigo-700 disabled:opacity-50">
            {loading ? "در حال ورود…" : "ورود به پنل"}
            {!loading && <ArrowLeft size={17} />}
          </button>
        </form>
      </div>
    </div>
  );
}
