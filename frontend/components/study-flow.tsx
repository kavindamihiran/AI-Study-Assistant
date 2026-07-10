import { Check, FileUp, MessageSquareText, WandSparkles } from "lucide-react";
import Link from "next/link";

type FlowStep = "sources" | "activity" | "learn";

const steps = [
  {
    id: "sources" as const,
    number: "01",
    label: "Add material",
    helper: "Upload your notes",
    href: "/documents",
    icon: FileUp,
  },
  {
    id: "activity" as const,
    number: "02",
    label: "Choose activity",
    helper: "Pick how to study",
    href: "/study-tools",
    icon: WandSparkles,
  },
  {
    id: "learn" as const,
    number: "03",
    label: "Learn & review",
    helper: "Chat or practise",
    href: "/chat",
    icon: MessageSquareText,
  },
];

export function StudyFlow({
  current,
  hasSources = false,
}: {
  current: FlowStep;
  hasSources?: boolean;
}) {
  const currentIndex = steps.findIndex((step) => step.id === current);

  return (
    <nav
      aria-label="Study progress"
      className="mt-6 overflow-hidden rounded-2xl border border-[#dfe5e1] bg-white shadow-[0_8px_30px_rgba(24,51,37,0.035)]"
    >
      <ol className="grid sm:grid-cols-3">
        {steps.map((step, index) => {
          const complete = index < currentIndex || (step.id === "sources" && hasSources && current !== "sources");
          const active = step.id === current;

          return (
            <li key={step.id} className="relative">
              {index > 0 && (
                <span className="absolute left-7 top-0 h-px w-[calc(100%-3.5rem)] bg-[#e2e7e4] sm:left-0 sm:top-1/2 sm:h-[calc(100%-2rem)] sm:w-px sm:-translate-y-1/2" />
              )}
              <Link
                href={step.href}
                aria-current={active ? "step" : undefined}
                className={`group flex items-center gap-3 px-4 py-3.5 transition sm:px-5 ${
                  active ? "bg-[#f1f8eb]" : "hover:bg-[#f8faf8]"
                }`}
              >
                <span
                  className={`grid size-9 shrink-0 place-items-center rounded-xl text-xs font-bold transition ${
                    active
                      ? "bg-[#173a29] text-[#c8f169]"
                      : complete
                        ? "bg-[#e8f3de] text-[#477238]"
                        : "bg-[#f0f3f1] text-[#7c8982]"
                  }`}
                >
                  {complete ? <Check size={15} strokeWidth={2.5} /> : <step.icon size={16} />}
                </span>
                <span className="min-w-0">
                  <span className="block text-[9px] font-bold uppercase tracking-[0.14em] text-[#8a958f]">
                    Step {step.number}
                  </span>
                  <span className={`mt-0.5 block text-sm font-semibold ${active ? "text-[#173a29]" : "text-[#405048]"}`}>
                    {step.label}
                  </span>
                  <span className="hidden text-[10px] text-[#8a958f] lg:block">
                    {step.helper}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
