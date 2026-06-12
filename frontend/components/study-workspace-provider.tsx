"use client";

import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  StudyWorkspace,
  createStudyWorkspace,
  deleteStudyWorkspace,
  getStudyWorkspaces,
} from "@/lib/api";

type StudyWorkspaceContextValue = {
  workspaces: StudyWorkspace[];
  activeWorkspace: StudyWorkspace | null;
  loading: boolean;
  createWorkspace: (title?: string) => Promise<StudyWorkspace>;
  deleteWorkspace: (workspaceId: string) => Promise<StudyWorkspace | null>;
  switchWorkspace: (workspaceId: string) => void;
  refreshWorkspaces: () => Promise<void>;
};

const STORAGE_KEY = "studyos.active-workspace-id.v1";
const StudyWorkspaceContext = createContext<StudyWorkspaceContextValue | null>(
  null,
);

export function StudyWorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<StudyWorkspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const activeWorkspace =
    workspaces.find((workspace) => workspace.id === activeWorkspaceId) ??
    workspaces[0] ??
    null;

  const refreshWorkspaces = useCallback(async () => {
    const loaded = await getStudyWorkspaces();
    setWorkspaces(loaded);
    const savedId = window.localStorage.getItem(STORAGE_KEY);
    if (savedId && loaded.some((workspace) => workspace.id === savedId)) {
      setActiveWorkspaceId(savedId);
    } else if (loaded[0]) {
      setActiveWorkspaceId(loaded[0].id);
      window.localStorage.setItem(STORAGE_KEY, loaded[0].id);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const loaded = await getStudyWorkspaces();
        if (loaded.length) {
          setWorkspaces(loaded);
          const savedId = window.localStorage.getItem(STORAGE_KEY);
          const active =
            loaded.find((workspace) => workspace.id === savedId) ?? loaded[0];
          setActiveWorkspaceId(active.id);
          window.localStorage.setItem(STORAGE_KEY, active.id);
        } else {
          const created = await createStudyWorkspace("General study session");
          setWorkspaces([created]);
          setActiveWorkspaceId(created.id);
          window.localStorage.setItem(STORAGE_KEY, created.id);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const createWorkspace = useCallback(async (title?: string) => {
    const created = await createStudyWorkspace(title || "New study session");
    setWorkspaces((current) => [created, ...current]);
    setActiveWorkspaceId(created.id);
    window.localStorage.setItem(STORAGE_KEY, created.id);
    return created;
  }, []);

  const deleteWorkspace = useCallback(
    async (workspaceId: string) => {
      await deleteStudyWorkspace(workspaceId);
      let loaded = await getStudyWorkspaces();
      if (!loaded.length) {
        const created = await createStudyWorkspace("General study session");
        loaded = [created];
      }

      const currentStillExists = loaded.find(
        (workspace) => workspace.id === activeWorkspaceId,
      );
      const nextActive =
        workspaceId === activeWorkspaceId || !currentStillExists
          ? loaded[0] ?? null
          : currentStillExists;

      setWorkspaces(loaded);
      setActiveWorkspaceId(nextActive?.id ?? null);
      if (nextActive) {
        window.localStorage.setItem(STORAGE_KEY, nextActive.id);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
      return nextActive;
    },
    [activeWorkspaceId],
  );

  const switchWorkspace = useCallback((workspaceId: string) => {
    setActiveWorkspaceId(workspaceId);
    window.localStorage.setItem(STORAGE_KEY, workspaceId);
  }, []);

  const value = useMemo(
    () => ({
      workspaces,
      activeWorkspace,
      loading,
      createWorkspace,
      deleteWorkspace,
      switchWorkspace,
      refreshWorkspaces,
    }),
    [
      activeWorkspace,
      createWorkspace,
      deleteWorkspace,
      loading,
      refreshWorkspaces,
      switchWorkspace,
      workspaces,
    ],
  );

  return (
    <StudyWorkspaceContext.Provider value={value}>
      {children}
    </StudyWorkspaceContext.Provider>
  );
}

export function useStudyWorkspace() {
  const context = useContext(StudyWorkspaceContext);
  if (!context) {
    throw new Error("useStudyWorkspace must be used inside StudyWorkspaceProvider");
  }
  return context;
}
