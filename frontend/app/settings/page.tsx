"use client";

import { Check, Database, KeyRound, Save, Server, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { ModelProfile, getActiveProfile, getProfiles, switchProfile } from "@/lib/api";

export default function SettingsPage() {
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [activeId, setActiveId] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void Promise.all([getProfiles(), getActiveProfile()]).then(([items, active]) => {
      setProfiles(items);
      setActiveId(active.profile_id);
    });
  }, []);

  async function save() {
    if (!activeId) return;
    await switchProfile(activeId);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  return (
    <AppShell>
      <PageHeading
        section="Settings"
        title="Workspace settings"
        description="Choose the default model and review how your local study workspace is connected."
      />
      <div className="mt-7 grid gap-6 xl:grid-cols-[1fr_340px]">
        <section className="rounded-3xl border border-[#dfe5e1] bg-white p-6">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-[#edf5e6] text-[#56843f]">
              <SlidersHorizontal size={18} />
            </div>
            <div>
              <h2 className="text-base font-semibold">Default model profile</h2>
              <p className="mt-1 text-xs text-[#7c8982]">Used for new chats and study tools</p>
            </div>
          </div>
          <div className="mt-6 space-y-3">
            {profiles.map((profile) => (
              <label
                key={profile.profile_id}
                className={`flex cursor-pointer items-center gap-4 rounded-2xl border p-4 ${
                  activeId === profile.profile_id
                    ? "border-[#82a874] bg-[#f4faef]"
                    : "border-[#e2e7e4]"
                }`}
              >
                <input
                  type="radio"
                  name="active-profile"
                  value={profile.profile_id}
                  checked={activeId === profile.profile_id}
                  onChange={() => setActiveId(profile.profile_id)}
                  className="sr-only"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold">{profile.display_name}</p>
                  <p className="mt-1 truncate font-mono text-[10px] text-[#89948e]">
                    {profile.model_id}
                  </p>
                </div>
                {activeId === profile.profile_id && (
                  <div className="grid size-6 place-items-center rounded-full bg-[#709b61] text-white">
                    <Check size={13} />
                  </div>
                )}
              </label>
            ))}
          </div>
          <button
            onClick={() => void save()}
            className="mt-6 flex items-center gap-2 rounded-xl bg-[#173a29] px-5 py-3 text-sm font-semibold text-white"
          >
            {saved ? <Check size={16} /> : <Save size={16} />}
            {saved ? "Saved" : "Save settings"}
          </button>
        </section>
        <aside className="space-y-4">
          {[
            {
              icon: Server,
              title: "FastAPI backend",
              text: "Connected on port 8000",
            },
            {
              icon: Database,
              title: "Vector database",
              text: "Not configured yet",
            },
            {
              icon: KeyRound,
              title: "Provider credentials",
              text: "Stored server-side only",
            },
          ].map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-[#dfe5e1] bg-white p-5"
            >
              <item.icon size={18} className="text-[#66806f]" />
              <p className="mt-3 text-sm font-semibold">{item.title}</p>
              <p className="mt-1 text-xs text-[#849089]">{item.text}</p>
            </div>
          ))}
        </aside>
      </div>
    </AppShell>
  );
}
