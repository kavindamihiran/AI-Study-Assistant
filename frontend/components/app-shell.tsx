"use client";

import {
  ChevronDown,
  CircleHelp,
  FileText,
  GraduationCap,
  History,
  LayoutDashboard,
  Library,
  Menu,
  MessageSquareText,
  LogOut,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
  WandSparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { useChatWorkspace } from "@/components/chat-provider";
import { useAuth } from "@/components/auth-provider";
import { useStudyJobs } from "@/components/study-job-provider";
import { useStudyWorkspace } from "@/components/study-workspace-provider";
import {
  ChatSessionSummary,
  DocumentRecord,
  getChatSession,
  getChatSessions,
  getDocuments,
} from "@/lib/api";

const workspaceItems = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Chat with notes", href: "/chat", icon: MessageSquareText },
  { label: "Documents", href: "/documents", icon: Library },
  { label: "Study tools", href: "/study-tools", icon: WandSparkles },
];

const manageItems = [
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
  const [sessionsOpen, setSessionsOpen] = useState(true);
  const [deletingWorkspaceId, setDeletingWorkspaceId] = useState<string | null>(
    null,
  );
  const [searchOpen, setSearchOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchDocuments, setSearchDocuments] = useState<DocumentRecord[]>([]);
  const [searchSessions, setSearchSessions] = useState<ChatSessionSummary[]>([]);
  const [shellError, setShellError] = useState("");
  const router = useRouter();
  const { user, logout } = useAuth();
  const { loadSession, startNewSession } = useChatWorkspace();
  const { clearJobs } = useStudyJobs();
  const {
    activeWorkspace,
    createWorkspace,
    deleteWorkspace,
    switchWorkspace,
    workspaces,
  } = useStudyWorkspace();
  const closeNav = () => setMobileNav(false);
  const allNavigationItems = useMemo(
    () => [...workspaceItems, ...manageItems],
    [],
  );
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const filteredNavigationItems = allNavigationItems.filter((item) =>
    item.label.toLowerCase().includes(normalizedSearch),
  );
  const filteredDocuments = searchDocuments.filter((document) =>
    `${document.title} ${document.filename}`.toLowerCase().includes(
      normalizedSearch,
    ),
  );
  const filteredSessions = searchSessions.filter((session) =>
    session.title.toLowerCase().includes(normalizedSearch),
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
      if (event.key === "Escape") {
        setSearchOpen(false);
        setHelpOpen(false);
        setProfileOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!activeWorkspace || (!searchOpen && !profileOpen)) return;
    void Promise.all([
      getDocuments(activeWorkspace.id),
      getChatSessions(activeWorkspace.id),
    ])
      .then(([documents, chatSessions]) => {
        setSearchDocuments(documents);
        setSearchSessions(chatSessions);
        setShellError("");
      })
      .catch((error) => {
        setShellError(
          error instanceof Error
            ? error.message
            : "Could not load workspace details.",
        );
      });
  }, [activeWorkspace?.id, profileOpen, searchOpen]);

  async function newStudySession() {
    await createWorkspace(`Study session ${workspaces.length + 1}`);
    startNewSession();
    clearJobs();
    closeNav();
    router.push("/chat");
  }

  async function removeStudySession(workspaceId: string, title: string) {
    const confirmed = window.confirm(
      `Delete "${title}" and all its uploaded documents, chats, and study outputs?`,
    );
    if (!confirmed) {
      return;
    }
    setDeletingWorkspaceId(workspaceId);
    try {
      await deleteWorkspace(workspaceId);
      startNewSession();
      clearJobs();
      closeNav();
      router.push("/chat");
    } finally {
      setDeletingWorkspaceId(null);
    }
  }

  function openSearch() {
    setSearchOpen(true);
    setProfileOpen(false);
    setHelpOpen(false);
  }

  function openHelp() {
    setHelpOpen(true);
    setProfileOpen(false);
    setSearchOpen(false);
  }

  function toggleProfile() {
    setProfileOpen((current) => !current);
    setHelpOpen(false);
    setSearchOpen(false);
  }

  function closePanels() {
    setSearchOpen(false);
    setHelpOpen(false);
    setProfileOpen(false);
  }

  function goTo(href: string) {
    closePanels();
    closeNav();
    router.push(href);
  }

  async function openChatSession(sessionIdToOpen: string) {
    const saved = await getChatSession(sessionIdToOpen);
    loadSession(saved);
    goTo("/chat");
  }

  const initials = user.display_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "U";

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
        className={`fixed inset-y-0 left-0 z-40 flex w-[290px] flex-col overflow-hidden border-r border-white/10 bg-[#10251c] px-4 py-5 text-white transition-transform lg:translate-x-0 ${
          mobileNav ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex shrink-0 items-center justify-between px-2">
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

        <div className="mt-6 min-h-0 flex-1 overflow-y-auto pr-1">
          <button
            onClick={() => void newStudySession()}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#c8f169] px-4 py-3 text-sm font-semibold text-[#17321f] transition hover:bg-[#d5f58a]"
          >
            <Plus size={17} />
            New study session
          </button>

          <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.055] p-3">
            <button
              onClick={() => setSessionsOpen((current) => !current)}
              className="flex w-full items-center justify-between gap-2 px-1 text-left"
            >
              <span className="min-w-0">
                <span className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-white/35">
                  Subject sessions
                </span>
                <span className="mt-2 block break-words text-xs font-semibold leading-5 text-white">
                  {activeWorkspace?.title ?? "Loading session..."}
                </span>
              </span>
              <ChevronDown
                size={15}
                className={`shrink-0 text-white/45 transition ${
                  sessionsOpen ? "rotate-180" : ""
                }`}
              />
            </button>
            {sessionsOpen && (
              <div className="mt-3 max-h-52 space-y-1 overflow-y-auto">
                {workspaces.map((workspace) => (
                  <div
                    key={workspace.id}
                    className={`flex items-center gap-2 rounded-xl border px-2 py-2 ${
                      workspace.id === activeWorkspace?.id
                        ? "border-white/10 bg-white/10 text-white"
                        : "border-transparent text-white/60 hover:border-white/10 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <button
                      onClick={() => {
                        switchWorkspace(workspace.id);
                        startNewSession();
                        clearJobs();
                        closeNav();
                      }}
                      className="min-w-0 flex-1 break-words text-left text-xs leading-5"
                    >
                      {workspace.title}
                    </button>
                    <button
                      onClick={() =>
                        void removeStudySession(workspace.id, workspace.title)
                      }
                      disabled={deletingWorkspaceId === workspace.id}
                      className="grid size-8 shrink-0 place-items-center rounded-lg border border-red-300/20 bg-red-400/10 text-red-100 transition hover:border-red-200/45 hover:bg-red-400/20 disabled:cursor-not-allowed disabled:opacity-50"
                      aria-label={`Delete ${workspace.title}`}
                      title={`Delete ${workspace.title}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <nav className="mt-6 space-y-1">
            <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">
              Workspace
            </p>
            {workspaceItems.map((item) => (
              <NavLink key={item.href} {...item} onNavigate={closeNav} />
            ))}
          </nav>

          <nav className="mt-6 space-y-1">
            <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">
              Manage
            </p>
            {manageItems.map((item) => (
              <NavLink key={item.href} {...item} onNavigate={closeNav} />
            ))}
          </nav>
        </div>

        <div className="mt-4 shrink-0 rounded-2xl border border-white/10 bg-white/[0.055] p-4">
          <div className="flex items-center gap-2 text-xs font-medium">
            <ShieldCheck size={15} className="text-[#c8f169]" />
            Private workspace
          </div>
          <p className="mt-2 text-[11px] leading-5 text-white/45">
            Your study material stays organized by subject session.
          </p>
        </div>
      </aside>

      <section className="lg:pl-[290px]">
        <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-[#dfe5e1] bg-[#f5f7f6]/90 px-5 backdrop-blur-xl md:px-8">
          <div className="flex items-center gap-3">
            <button
              className="rounded-xl border border-[#dce3de] bg-white p-2.5 lg:hidden"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              <Menu size={18} />
            </button>
            <button
              onClick={openSearch}
              className="hidden items-center gap-2 rounded-xl border border-[#dce3de] bg-white px-3 py-2.5 text-left text-sm text-[#6e7c75] shadow-sm transition hover:border-[#b8c8bf] hover:text-[#263b30] sm:flex sm:w-[280px]"
              aria-label="Search your workspace"
            >
              <Search size={16} />
              <span>Search your workspace</span>
              <span className="ml-auto rounded-md bg-[#f0f3f1] px-1.5 py-0.5 text-[10px]">
                Ctrl K
              </span>
            </button>
          </div>
          <div className="relative flex items-center gap-3">
            <button
              onClick={openHelp}
              className="grid size-9 place-items-center rounded-full border border-[#dce3de] bg-white text-[#65736c] transition hover:border-[#b8c8bf] hover:text-[#263b30]"
              aria-label="Open help"
            >
              <CircleHelp size={17} />
            </button>
            <div className="h-7 w-px bg-[#dce3de]" />
            <button
              onClick={toggleProfile}
              className="flex items-center gap-2 rounded-2xl px-1.5 py-1 transition hover:bg-white"
              aria-label="Open profile menu"
            >
              <div className="grid size-9 place-items-center rounded-full bg-[#dce8ff] text-xs font-bold text-[#315baa]">
                {initials}
              </div>
              <div className="hidden sm:block">
                <p className="max-w-32 truncate text-xs font-semibold">
                  {user.display_name}
                </p>
                <p className="text-[10px] text-[#849089]">Student workspace</p>
              </div>
              <ChevronDown size={14} className="text-[#7d8982]" />
            </button>
            {profileOpen && (
              <div className="absolute right-0 top-12 z-50 w-[290px] rounded-3xl border border-[#dfe5e1] bg-white p-4 shadow-[0_24px_70px_rgba(21,43,31,0.18)]">
                <div className="flex items-center gap-3">
                  <div className="grid size-11 place-items-center rounded-full bg-[#dce8ff] text-sm font-bold text-[#315baa]">
                    {initials}
                  </div>
                  <div>
                    <p className="text-sm font-semibold">{user.display_name}</p>
                    <p className="text-xs text-[#7c8982]">{user.email}</p>
                  </div>
                </div>
                <div className="mt-4 rounded-2xl bg-[#f7f9f7] p-3 text-xs leading-5 text-[#65736c]">
                  <p>
                    <span className="font-semibold text-[#263b30]">Session:</span>{" "}
                    {activeWorkspace?.title ?? "Loading..."}
                  </p>
                  <p>
                    <span className="font-semibold text-[#263b30]">Docs:</span>{" "}
                    {searchDocuments.length} in this session
                  </p>
                </div>
                {shellError && (
                  <p className="mt-3 rounded-xl bg-red-50 p-3 text-xs text-red-700">
                    {shellError}
                  </p>
                )}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button
                    onClick={() => goTo("/documents")}
                    className="rounded-xl border border-[#dfe5e1] px-3 py-2 text-xs font-semibold hover:bg-[#f7f9f7]"
                  >
                    Documents
                  </button>
                  <button
                    onClick={() => goTo("/settings")}
                    className="rounded-xl border border-[#dfe5e1] px-3 py-2 text-xs font-semibold hover:bg-[#f7f9f7]"
                  >
                    Settings
                  </button>
                </div>
                <button
                  onClick={() => void logout()}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-red-100 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50"
                >
                  <LogOut size={14} />
                  Sign out
                </button>
              </div>
            )}
          </div>
        </header>
        <div className="mx-auto max-w-[1450px] px-5 py-8 md:px-8 lg:px-10">
          {children}
        </div>
      </section>
      {searchOpen && (
        <div className="fixed inset-0 z-[70] bg-[#10251c]/35 p-4 backdrop-blur-sm">
          <div className="mx-auto mt-12 max-w-2xl overflow-hidden rounded-3xl border border-[#dfe5e1] bg-white shadow-[0_24px_80px_rgba(21,43,31,0.22)]">
            <div className="flex items-center gap-3 border-b border-[#e2e7e4] px-5 py-4">
              <Search size={18} className="text-[#66806f]" />
              <input
                autoFocus
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search pages, documents, or saved chats..."
                className="min-w-0 flex-1 bg-transparent text-sm outline-none"
              />
              <button
                onClick={closePanels}
                className="rounded-lg px-2 py-1 text-xs font-semibold text-[#7c8982] hover:bg-[#f3f6f3]"
              >
                Esc
              </button>
            </div>
            <div className="max-h-[65vh] overflow-y-auto p-4">
              {shellError && (
                <p className="mb-3 rounded-xl bg-red-50 p-3 text-xs text-red-700">
                  {shellError}
                </p>
              )}
              <SearchSection title="Pages">
                {filteredNavigationItems.map((item) => (
                  <button
                    key={item.href}
                    onClick={() => goTo(item.href)}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm hover:bg-[#f7f9f7]"
                  >
                    <item.icon size={16} className="text-[#66806f]" />
                    <span>{item.label}</span>
                  </button>
                ))}
              </SearchSection>
              <SearchSection title="Documents">
                {!filteredDocuments.length && (
                  <p className="px-3 py-2 text-xs text-[#89948e]">
                    No matching documents in this session.
                  </p>
                )}
                {filteredDocuments.slice(0, 8).map((document) => (
                  <button
                    key={document.id}
                    onClick={() => goTo("/documents")}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left hover:bg-[#f7f9f7]"
                  >
                    <FileText size={16} className="shrink-0 text-[#66806f]" />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">
                        {document.filename}
                      </span>
                      <span className="mt-0.5 block text-[10px] text-[#89948e]">
                        {document.chunk_count} chunks · {document.status}
                      </span>
                    </span>
                  </button>
                ))}
              </SearchSection>
              <SearchSection title="Saved Chats">
                {!filteredSessions.length && (
                  <p className="px-3 py-2 text-xs text-[#89948e]">
                    No matching chats in this session.
                  </p>
                )}
                {filteredSessions.slice(0, 8).map((session) => (
                  <button
                    key={session.id}
                    onClick={() => void openChatSession(session.id)}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left hover:bg-[#f7f9f7]"
                  >
                    <History size={16} className="shrink-0 text-[#66806f]" />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">
                        {session.title}
                      </span>
                      <span className="mt-0.5 block text-[10px] text-[#89948e]">
                        saved conversation
                      </span>
                    </span>
                  </button>
                ))}
              </SearchSection>
            </div>
          </div>
        </div>
      )}
      {helpOpen && (
        <div className="fixed inset-0 z-[70] bg-[#10251c]/35 p-4 backdrop-blur-sm">
          <div className="mx-auto mt-16 max-w-lg rounded-3xl border border-[#dfe5e1] bg-white p-6 shadow-[0_24px_80px_rgba(21,43,31,0.22)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#66806f]">
                  Help
                </p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
                  How StudyOS works
                </h2>
              </div>
              <button
                onClick={closePanels}
                className="rounded-xl border border-[#dfe5e1] p-2 text-[#65736c] hover:bg-[#f7f9f7]"
                aria-label="Close help"
              >
                <X size={16} />
              </button>
            </div>
            <div className="mt-5 space-y-3 text-sm leading-6 text-[#65736c]">
              <p>
                Use subject sessions to keep each module separate. Upload PDFs
                or notes inside the active session, then chat or generate study
                material from those documents.
              </p>
              <p>
                Press <span className="font-semibold text-[#263b30]">Ctrl K</span>{" "}
                to search pages, uploaded documents, and saved chats.
              </p>
              <p>
                Chat and study-tool jobs keep processing while you move between
                pages.
              </p>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-2">
              <button
                onClick={() => goTo("/documents")}
                className="rounded-xl bg-[#173a29] px-4 py-3 text-xs font-semibold text-white"
              >
                Upload docs
              </button>
              <button
                onClick={() => goTo("/study-tools")}
                className="rounded-xl border border-[#dfe5e1] px-4 py-3 text-xs font-semibold"
              >
                Study tools
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function SearchSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="mb-4 last:mb-0">
      <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#8a958f]">
        {title}
      </p>
      <div>{children}</div>
    </section>
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
