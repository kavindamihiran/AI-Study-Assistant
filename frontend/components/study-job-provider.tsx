"use client";

import { CheckCircle2, Clock3, LoaderCircle, XCircle } from "lucide-react";
import Link from "next/link";
import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  StudyToolKind,
  StudyToolResponse,
  generateStudyTool,
} from "@/lib/api";

type StudyJobStatus = "queued" | "running" | "completed" | "failed";

export type StudyJob = {
  id: string;
  tool: StudyToolKind;
  documentIds: string[];
  sourceNames: string[];
  topic: string;
  profileId?: string;
  status: StudyJobStatus;
  result: StudyToolResponse | null;
  error: string | null;
  createdAt: number;
  updatedAt: number;
};

type EnqueueStudyJob = Pick<
  StudyJob,
  "tool" | "documentIds" | "sourceNames" | "topic" | "profileId"
>;

type StudyJobContextValue = {
  jobs: StudyJob[];
  selectedJob: StudyJob | null;
  enqueue: (input: EnqueueStudyJob) => string;
  selectJob: (jobId: string | null) => void;
};

const STORAGE_KEY = "studyos.study-jobs.v1";
const MAX_SAVED_JOBS = 20;
const StudyJobContext = createContext<StudyJobContextValue | null>(null);

function createJobId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function toolLabel(tool: StudyToolKind) {
  return {
    summary: "Summary",
    mcq: "MCQs",
    flashcards: "Flashcards",
    plan: "Study plan",
  }[tool];
}

export function StudyJobProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<StudyJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const processingRef = useRef(false);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as {
          jobs?: StudyJob[];
          selectedJobId?: string | null;
        };
        const restored = (parsed.jobs ?? []).map((job) => ({
          ...job,
          status: job.status === "running" ? ("queued" as const) : job.status,
        }));
        setJobs(restored);
        setSelectedJobId(parsed.selectedJobId ?? restored[0]?.id ?? null);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        jobs: jobs.slice(0, MAX_SAVED_JOBS),
        selectedJobId,
      }),
    );
  }, [hydrated, jobs, selectedJobId]);

  useEffect(() => {
    if (!hydrated || processingRef.current) return;
    if (jobs.some((job) => job.status === "running")) return;
    const nextJob = [...jobs]
      .reverse()
      .find((job) => job.status === "queued");
    if (!nextJob) return;

    processingRef.current = true;
    setJobs((current) =>
      current.map((job) =>
        job.id === nextJob.id
          ? { ...job, status: "running", updatedAt: Date.now() }
          : job,
      ),
    );

    void generateStudyTool(
      nextJob.tool,
      nextJob.documentIds,
      nextJob.topic,
      nextJob.profileId,
    )
      .then((result) => {
        setJobs((current) =>
          current.map((job) =>
            job.id === nextJob.id
              ? {
                  ...job,
                  status: "completed",
                  result,
                  error: null,
                  updatedAt: Date.now(),
                }
              : job,
          ),
        );
      })
      .catch((error) => {
        setJobs((current) =>
          current.map((job) =>
            job.id === nextJob.id
              ? {
                  ...job,
                  status: "failed",
                  error:
                    error instanceof Error ? error.message : "Generation failed.",
                  updatedAt: Date.now(),
                }
              : job,
          ),
        );
      })
      .finally(() => {
        processingRef.current = false;
        setJobs((current) => [...current]);
      });
  }, [hydrated, jobs]);

  const enqueue = useCallback((input: EnqueueStudyJob) => {
    const id = createJobId();
    const now = Date.now();
    const job: StudyJob = {
      ...input,
      id,
      status: "queued",
      result: null,
      error: null,
      createdAt: now,
      updatedAt: now,
    };
    setJobs((current) => [job, ...current].slice(0, MAX_SAVED_JOBS));
    setSelectedJobId(id);
    return id;
  }, []);

  const selectJob = useCallback((jobId: string | null) => {
    setSelectedJobId(jobId);
  }, []);

  const selectedJob =
    jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null;
  const value = useMemo(
    () => ({ jobs, selectedJob, enqueue, selectJob }),
    [enqueue, jobs, selectJob, selectedJob],
  );

  return (
    <StudyJobContext.Provider value={value}>
      {children}
      <GlobalJobStatus jobs={jobs} selectJob={selectJob} />
    </StudyJobContext.Provider>
  );
}

function GlobalJobStatus({
  jobs,
  selectJob,
}: {
  jobs: StudyJob[];
  selectJob: (jobId: string) => void;
}) {
  const [hiddenJobId, setHiddenJobId] = useState<string | null>(null);
  const active = jobs.find(
    (job) => job.status === "running" || job.status === "queued",
  );
  const latest = active ?? jobs[0];

  useEffect(() => {
    if (!latest) return;
    setHiddenJobId(null);
    if (latest.status === "running" || latest.status === "queued") return;
    const timer = window.setTimeout(() => {
      setHiddenJobId(latest.id);
    }, 6000);
    return () => window.clearTimeout(timer);
  }, [latest?.id, latest?.status]);

  if (!latest || latest.id === hiddenJobId) return null;

  const queuedCount = jobs.filter((job) => job.status === "queued").length;
  const statusText =
    latest.status === "running"
      ? `Generating ${toolLabel(latest.tool)}`
      : latest.status === "queued"
        ? `Queued ${toolLabel(latest.tool)}`
        : latest.status === "completed"
          ? `${toolLabel(latest.tool)} ready`
          : `${toolLabel(latest.tool)} failed`;

  return (
    <Link
      href="/study-tools"
      onClick={() => selectJob(latest.id)}
      className="fixed bottom-5 right-5 z-50 flex max-w-[330px] items-center gap-3 rounded-2xl border border-[#d9e3dc] bg-white px-4 py-3 shadow-[0_16px_45px_rgba(21,43,31,0.18)] transition hover:-translate-y-0.5"
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#eef5ea] text-[#477238]">
        {latest.status === "running" && (
          <LoaderCircle size={18} className="animate-spin" />
        )}
        {latest.status === "queued" && <Clock3 size={18} />}
        {latest.status === "completed" && <CheckCircle2 size={18} />}
        {latest.status === "failed" && <XCircle size={18} className="text-[#a44835]" />}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-[#263b30]">
          {statusText}
        </span>
        <span className="block truncate text-xs text-[#75827b]">
          {latest.sourceNames.join(", ")}
          {queuedCount > 0 && latest.status === "running"
            ? ` · ${queuedCount} waiting`
            : ""}
        </span>
      </span>
    </Link>
  );
}

export function useStudyJobs() {
  const context = useContext(StudyJobContext);
  if (!context) {
    throw new Error("useStudyJobs must be used inside StudyJobProvider");
  }
  return context;
}
