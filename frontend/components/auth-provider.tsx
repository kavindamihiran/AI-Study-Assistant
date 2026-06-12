"use client";

import { GraduationCap, LoaderCircle, LockKeyhole } from "lucide-react";
import {
  FormEvent,
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AuthUser,
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  setCsrfToken,
} from "@/lib/api";

type AuthContextValue = {
  user: AuthUser;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const LAST_USER_KEY = "studyos.last-user-id.v1";
const USER_STATE_KEYS = [
  "studyos.active-workspace-id.v1",
  "studyos.chat.v1",
  "studyos.study-jobs.v1",
];

function clearUserState() {
  for (const key of USER_STATE_KEYS) {
    window.localStorage.removeItem(key);
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const acceptUser = useCallback((nextUser: AuthUser) => {
    const previousUserId = window.localStorage.getItem(LAST_USER_KEY);
    if (previousUserId && previousUserId !== nextUser.id) {
      clearUserState();
    }
    window.localStorage.setItem(LAST_USER_KEY, nextUser.id);
    setUser(nextUser);
  }, []);

  useEffect(() => {
    void getCurrentUser()
      .then(acceptUser)
      .catch(() => {
        setCsrfToken("");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [acceptUser]);

  useEffect(() => {
    function onAuthRequired() {
      clearUserState();
      window.localStorage.removeItem(LAST_USER_KEY);
      setCsrfToken("");
      setUser(null);
    }
    window.addEventListener("studyos-auth-required", onAuthRequired);
    return () =>
      window.removeEventListener("studyos-auth-required", onAuthRequired);
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      clearUserState();
      window.localStorage.removeItem(LAST_USER_KEY);
      setCsrfToken("");
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => (user ? { user, logout } : null),
    [logout, user],
  );

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f5f7f6]">
        <LoaderCircle className="animate-spin text-[#477238]" size={26} />
      </main>
    );
  }

  if (!user) {
    return <AuthScreen onAuthenticated={acceptUser} />;
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const authenticated =
        mode === "register"
          ? await registerRequest(displayName, email, password)
          : await loginRequest(email, password);
      onAuthenticated(authenticated);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Authentication failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#10251c] px-5 py-10 text-[#18251f]">
      <div className="mx-auto grid min-h-[calc(100vh-5rem)] max-w-5xl overflow-hidden rounded-[32px] bg-white shadow-[0_30px_100px_rgba(0,0,0,0.28)] lg:grid-cols-[1.05fr_0.95fr]">
        <section className="hidden bg-[#173a29] p-12 text-white lg:block">
          <div className="grid size-12 place-items-center rounded-2xl bg-[#c8f169] text-[#17321f]">
            <GraduationCap size={25} />
          </div>
          <h1 className="mt-10 max-w-md text-4xl font-semibold tracking-[-0.04em]">
            A secure AI study workspace for every learner
          </h1>
          <p className="mt-5 max-w-md text-sm leading-7 text-white/60">
            Create an account to keep uploaded material, subject sessions, and
            saved conversations isolated to you.
          </p>
          <div className="mt-10 flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 text-xs text-white/65">
            <LockKeyhole size={18} className="text-[#c8f169]" />
            Secure cookie sessions and server-enforced ownership
          </div>
        </section>

        <section className="flex items-center p-7 sm:p-12">
          <div className="w-full">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#66806f]">
              StudyOS
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.035em]">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h2>
            <p className="mt-2 text-sm text-[#7c8982]">
              {mode === "login"
                ? "Sign in to continue to your study sessions."
                : "Anyone can join. Use a strong password with at least 12 characters."}
            </p>

            <form onSubmit={submit} className="mt-8 space-y-4">
              {mode === "register" && (
                <label className="block">
                  <span className="text-xs font-semibold text-[#405149]">
                    Display name
                  </span>
                  <input
                    required
                    maxLength={120}
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    autoComplete="name"
                    className="mt-2 w-full rounded-xl border border-[#dce3de] px-4 py-3 text-sm outline-none focus:border-[#6e947a]"
                  />
                </label>
              )}
              <label className="block">
                <span className="text-xs font-semibold text-[#405149]">
                  Email
                </span>
                <input
                  required
                  type="email"
                  maxLength={320}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  className="mt-2 w-full rounded-xl border border-[#dce3de] px-4 py-3 text-sm outline-none focus:border-[#6e947a]"
                />
              </label>
              <label className="block">
                <span className="text-xs font-semibold text-[#405149]">
                  Password
                </span>
                <input
                  required
                  type="password"
                  minLength={mode === "register" ? 12 : 1}
                  maxLength={128}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  className="mt-2 w-full rounded-xl border border-[#dce3de] px-4 py-3 text-sm outline-none focus:border-[#6e947a]"
                />
              </label>

              {error && (
                <p className="rounded-xl bg-red-50 px-4 py-3 text-xs text-red-700">
                  {error}
                </p>
              )}

              <button
                disabled={submitting}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#173a29] px-4 py-3.5 text-sm font-semibold text-white disabled:opacity-60"
              >
                {submitting && (
                  <LoaderCircle size={16} className="animate-spin" />
                )}
                {mode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>

            <button
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
              className="mt-5 text-sm font-semibold text-[#477238]"
            >
              {mode === "login"
                ? "Need an account? Register"
                : "Already have an account? Sign in"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
