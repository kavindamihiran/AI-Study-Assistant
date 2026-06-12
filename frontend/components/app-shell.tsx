"use client";

import {
  Activity,
  ChevronDown,
  CircleHelp,
  GraduationCap,
  LayoutDashboard,
  Library,
  Menu,
  MessageSquareText,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  WandSparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useState } from "react";

const workspaceItems = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Chat with notes", href: "/chat", icon: MessageSquareText },
  { label: "Documents", href: "/documents", icon: Library },
  { label: "Study tools", href: "/study-tools", icon: WandSparkles },
];

const manageItems = [
  { label: "Model gateway", href: "/gateway", icon: Activity },
  { label: "Settings", href: "/settings", icon: Settings2 },
];

function NavLink({
  href,
  label,
  icon: Icon,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  onNavigate: () => void;
}) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
        active
          ? "bg-white/10 font-medium text-white"
          : "text-white/55 hover:bg-white/5 hover:text-white"
      }`}
    >
      <Icon size={17} />
      {label}
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileNav, setMobileNav] = useState(false);
  const closeNav = () => setMobileNav(false);

  return (
    <main className="min-h-screen bg-[#f5f7f6] text-[#18251f]">
      {mobileNav && (
        <button
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
          onClick={closeNav}
          aria-label="Close navigation overlay"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[250px] border-r border-white/10 bg-[#10251c] px-4 py-5 text-white transition-transform lg:translate-x-0 ${
          mobileNav ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-2">
          <Link href="/" className="flex items-center gap-3" onClick={closeNav}>
            <div className="grid size-10 place-items-center rounded-xl bg-[#c8f169] text-[#17321f] shadow-[0_8px_24px_rgba(200,241,105,0.22)]">
              <GraduationCap size={22} strokeWidth={2.4} />
            </div>
            <div>
              <p className="text-[17px] font-semibold tracking-tight">StudyOS</p>
              <p className="text-[10px] uppercase tracking-[0.18em] text-white/45">
                AI workspace
              </p>
            </div>
          </Link>
          <button
            className="rounded-lg p-2 text-white/60 hover:bg-white/10 lg:hidden"
            onClick={closeNav}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <Link
          href="/chat"
          onClick={closeNav}
          className="mt-7 flex w-full items-center justify-center gap-2 rounded-xl bg-[#c8f169] px-4 py-3 text-sm font-semibold text-[#17321f] transition hover:bg-[#d5f58a]"
        >
          <Plus size={17} />
          New study session
        </Link>

        <nav className="mt-7 space-y-1">
          <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">
            Workspace
          </p>
          {workspaceItems.map((item) => (
            <NavLink key={item.href} {...item} onNavigate={closeNav} />
          ))}
        </nav>

        <nav className="mt-7 space-y-1">
          <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">
            Manage
          </p>
          {manageItems.map((item) => (
            <NavLink key={item.href} {...item} onNavigate={closeNav} />
          ))}
        </nav>

        <div className="absolute bottom-5 left-4 right-4 rounded-2xl border border-white/10 bg-white/[0.055] p-4">
          <div className="flex items-center gap-2 text-xs font-medium">
            <ShieldCheck size={15} className="text-[#c8f169]" />
            Gateway protected
          </div>
          <p className="mt-2 text-[11px] leading-5 text-white/45">
            Provider secrets stay server-side. Hidden reasoning is never exposed.
          </p>
        </div>
      </aside>

      <section className="lg:pl-[250px]">
        <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-[#dfe5e1] bg-[#f5f7f6]/90 px-5 backdrop-blur-xl md:px-8">
          <div className="flex items-center gap-3">
            <button
              className="rounded-xl border border-[#dce3de] bg-white p-2.5 lg:hidden"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              <Menu size={18} />
            </button>
            <div className="hidden items-center gap-2 rounded-xl border border-[#dce3de] bg-white px-3 py-2.5 text-sm text-[#6e7c75] shadow-sm sm:flex sm:w-[280px]">
              <Search size={16} />
              <span>Search your workspace</span>
              <span className="ml-auto rounded-md bg-[#f0f3f1] px-1.5 py-0.5 text-[10px]">
                Ctrl K
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button className="grid size-9 place-items-center rounded-full border border-[#dce3de] bg-white text-[#65736c]">
              <CircleHelp size={17} />
            </button>
            <div className="h-7 w-px bg-[#dce3de]" />
            <div className="flex items-center gap-2">
              <div className="grid size-9 place-items-center rounded-full bg-[#dce8ff] text-xs font-bold text-[#315baa]">
                KS
              </div>
              <div className="hidden sm:block">
                <p className="text-xs font-semibold">Kavinda</p>
                <p className="text-[10px] text-[#849089]">Student workspace</p>
              </div>
              <ChevronDown size={14} className="text-[#7d8982]" />
            </div>
          </div>
        </header>
        <div className="mx-auto max-w-[1450px] px-5 py-8 md:px-8 lg:px-10">
          {children}
        </div>
      </section>
    </main>
  );
}

export function PageHeading({
  section,
  title,
  description,
  action,
}: {
  section: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[#66806f]">
          <span>Workspace</span>
          <span>/</span>
          <span className="text-[#263b30]">{section}</span>
        </div>
        <h1 className="text-3xl font-semibold tracking-[-0.035em] md:text-[38px]">
          {title}
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#6f7d76]">
          {description}
        </p>
      </div>
      {action}
    </div>
  );
}

