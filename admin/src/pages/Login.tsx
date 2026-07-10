import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, setToken } from "../api/client";
import BrandLogo from "../components/BrandLogo";

const inputClass =
  "w-full h-12 bg-zinc-50 border border-zinc-200 rounded-lg px-4 text-sm focus:outline-none focus:bg-white focus:border-violet-500 focus:ring-2 focus:ring-violet-500/15";

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
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-1 bg-zinc-950 text-white flex-col justify-between p-16">
        <BrandLogo size="lg" />
        <div>
          <h1 className="text-5xl font-black leading-[1.15] tracking-tight">
            مدیریت
            <br />
            <span className="text-violet-400">gateway</span>
          </h1>
          <p className="mt-6 text-zinc-500 text-lg max-w-sm leading-relaxed">
            پنل ادمین برای کاربران، کلیدها و مصرف توکن
          </p>
        </div>
        <p className="text-zinc-700 text-sm">llm_fastapi</p>
      </div>

      <div className="flex-1 flex items-center justify-center p-8 bg-zinc-100">
        <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
          <div>
            <h2 className="text-2xl font-black text-zinc-900">ورود</h2>
            <p className="text-zinc-500 text-sm mt-1">حساب superuser</p>
          </div>
          {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-100 rounded-lg px-4 py-3">{error}</p>}
          <label className="block space-y-2">
            <span className="text-sm font-semibold text-zinc-700">نام کاربری</span>
            <input className={inputClass} value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          </label>
          <label className="block space-y-2">
            <span className="text-sm font-semibold text-zinc-700">رمز عبور</span>
            <input type="password" className={inputClass} value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <button type="submit" disabled={loading} className="w-full h-12 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-bold text-sm transition-colors disabled:opacity-50">
            {loading ? "ورود…" : "ادامه"}
          </button>
        </form>
      </div>
    </div>
  );
}
