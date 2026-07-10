import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { clearToken } from "../api/client";
import BrandLogo from "./BrandLogo";

const links = [
  { to: "/", end: true, label: "داشبورد" },
  { to: "/users", label: "کاربران" },
  { to: "/api-keys", label: "کلیدهای API" },
  { to: "/usage", label: "مصرف توکن" },
];

function navClass({ isActive }: { isActive: boolean }) {
  return `block px-3.5 py-2.5 rounded-md text-[15px] font-semibold transition-colors ${
    isActive
      ? "bg-zinc-800 text-white"
      : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50"
  }`;
}

export default function Layout() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex bg-zinc-100">
      <aside className="w-60 shrink-0 bg-zinc-950 text-white flex flex-col border-l border-zinc-800">
        <div className="px-5 py-6 border-b border-zinc-800/80">
          <BrandLogo size="md" />
        </div>

        <nav className="flex-1 p-3 space-y-0.5">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className={navClass}>
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-zinc-800/80">
          <button
            type="button"
            onClick={() => { clearToken(); navigate("/login"); }}
            className="w-full text-right px-3.5 py-2.5 text-[15px] text-zinc-500 hover:text-zinc-200 rounded-md hover:bg-zinc-800/50 transition-colors"
          >
            خروج
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="shrink-0 h-14 flex items-center px-8 border-b border-zinc-200/80 bg-white/80 backdrop-blur-sm">
          <p className="text-sm text-zinc-500">
            {new Date().toLocaleDateString("fa-IR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
        </header>
        <main className="flex-1 w-full px-8 py-8 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
