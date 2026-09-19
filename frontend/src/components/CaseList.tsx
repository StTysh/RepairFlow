import type { components } from "../api/schema";
import { formatRelative, titleCase } from "../lib/format";

type CaseListItem = components["schemas"]["CaseListItem"];

const STATUS_DOT: Record<string, string> = {
  ACTIVE: "bg-sky-400",
  AWAITING_CONFIRMATION: "bg-violet-400",
  RESOLVED: "bg-emerald-400",
  ESCALATED: "bg-rose-400",
  CANCELLED: "bg-slate-500",
};

export function CaseList({
  items,
  selectedCaseId,
  onSelect,
}: {
  items: CaseListItem[];
  selectedCaseId: string | null;
  onSelect: (id: string) => void;
}) {
  if (items.length === 0) {
    return <p className="p-4 text-xs text-slate-500">No cases yet — start one from demo controls.</p>;
  }

  return (
    <ul className="divide-y divide-slate-800">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            onClick={() => onSelect(item.id)}
            className={`flex w-full flex-col gap-0.5 px-4 py-2.5 text-left hover:bg-slate-800/60 ${
              item.id === selectedCaseId ? "bg-slate-800/80" : ""
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[item.status] ?? "bg-slate-600"}`} />
              <span className="truncate text-xs font-medium text-slate-200">{item.title}</span>
            </div>
            <span className="pl-3.5 text-[10px] text-slate-500">
              {titleCase(item.status)} · v{item.version} · {formatRelative(item.updated_at)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
