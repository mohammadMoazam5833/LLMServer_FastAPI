import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Gauge,
  KeyRound,
  LogOut,
  Menu,
  Network,
  UsersRound,
  X,
} from "lucide-react";
import { clearToken } from "../api/client";
import BrandLogo from "./BrandLogo";

const links = [
  { to: "/", end: true, label: "نمای کلی", short: "داشبورد", icon: Gauge },
  { to: "/models", label: "ارائه‌دهندگان و مدل‌ها", short: "مدل‌ها", icon: Network },
  { to: "/users", label: "کاربران", short: "کاربران", icon: UsersRound },
  { to: "/api-keys", label: "کلیدهای دسترسی", short: "کلیدها", icon: KeyRound },
  { to: "/usage", label: "مصرف و متریک‌ها", short: "مصرف", icon: Activity },
];

function navClass({ isActive }: { isActive: boolean }) {
  return `group flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-semibold transition-all ${
    isActive
      ? "bg-white/[0.09] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,.06)]"
      : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.05]"
  }`;
}

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const activePage = links.find((link) =>
    link.to === "/" ? location.pathname === "/" : location.pathname.startsWith(link.to),
  );

  function logout() {
    clearToken();
    navigate("/login");
  }

  const sidebar = (
    <>
      <div className="h-20 px-5 flex items-center justify-between border-b border-white/[0.07]">
        <BrandLogo size="sm" />
        <button
          type="button"
          onClick={() => setMobileOpen(false)}
          className="lg:hidden grid size-9 place-items-center rounded-lg text-slate-400 hover:bg-white/5 hover:text-white"
          aria-label="بستن منو"
        >
          <X size={18} />
        </button>
      </div>

      <div className="px-4 pt-6 pb-2">
        <p className="px-3 text-[10px] font-bold tracking-[0.16em] text-slate-600 uppercase">
          مدیریت سامانه
        </p>
      </div>
      <nav className="flex-1 px-3 space-y-1">
        {links.map((link) => {
          const Icon = link.icon;
          return (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={navClass}
              onClick={() => setMobileOpen(false)}
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`grid size-8 shrink-0 place-items-center rounded-lg transition-colors ${
                      isActive ? "bg-indigo-500 text-white" : "bg-white/[0.04] text-slate-500 group-hover:text-slate-300"
                    }`}
                  >
                    <Icon size={16} strokeWidth={2} />
                  </span>
                  <span className="truncate">{link.label}</span>
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="p-3">
        <div className="mb-3 rounded-xl border border-white/[0.07] bg-white/[0.035] p-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-40" />
              <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
            </span>
            Gateway در دسترس
          </div>
          <p className="mt-1.5 text-[10px] leading-5 text-slate-600">کنترل‌پلین LLM Gateway</p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-500 transition-colors hover:bg-rose-500/10 hover:text-rose-300"
        >
          <LogOut size={16} />
          خروج از حساب
        </button>
      </div>
    </>
  );

  return (
    <div className="min-h-screen bg-[#f7f8fa] lg:flex">
      <aside className="fixed inset-y-0 right-0 z-40 hidden w-[264px] flex-col bg-[#0b1120] text-white lg:flex">
        {sidebar}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/45 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-label="بستن منو"
          />
          <aside className="absolute inset-y-0 right-0 flex w-[284px] flex-col bg-[#0b1120] text-white shadow-2xl">
            {sidebar}
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1 lg:mr-[264px]">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/85 px-4 backdrop-blur-xl sm:px-7">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="grid size-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 lg:hidden"
              aria-label="باز کردن منو"
            >
              <Menu size={19} />
            </button>
            <div>
              <p className="text-sm font-bold text-slate-800">{activePage?.short ?? "مدیریت"}</p>
              <p className="hidden text-[11px] text-slate-400 sm:block">
                {new Date().toLocaleDateString("fa-IR", { weekday: "long", day: "numeric", month: "long" })}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold text-slate-500 sm:flex">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              محیط اصلی
            </div>
            <div className="grid size-9 place-items-center rounded-xl bg-slate-900 text-xs font-black text-white">
              AD
            </div>
          </div>
        </header>
        <main className="w-full px-4 py-6 sm:px-7 sm:py-8 xl:px-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
