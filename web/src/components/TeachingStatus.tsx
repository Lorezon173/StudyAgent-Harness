import { ChatResponse } from "../types";

export default function TeachingStatus({ last }: { last: ChatResponse | null }) {
  if (!last) return null;
  const score = last.mastery_score ?? null;
  const modes = last.mode_path ?? [];
  return (
    <div
      style={{
        display: "flex",
        gap: 16,
        alignItems: "center",
        padding: "8px 12px",
        background: "#fff",
        borderBottom: "1px solid #e3e6ea",
        fontSize: 13,
        flexWrap: "wrap",
      }}
    >
      <span>
        掌握度：
        <progress
          max={100}
          value={score ?? 0}
          style={{ verticalAlign: "middle" }}
        />
        {score === null ? " —" : ` ${score}`}
      </span>
      <span>
        模式：
        {modes.length ? (
          modes.map((m, i) => (
            <span
              key={i}
              style={{
                background: "#eef2f7",
                borderRadius: 4,
                padding: "1px 6px",
                marginLeft: 4,
              }}
            >
              {m}
            </span>
          ))
        ) : (
          " —"
        )}
      </span>
      <span>回合：{last.turn_count ?? "—"}</span>
      <span style={{ marginLeft: "auto", color: "#888" }}>
        栈：{last.stack ?? "—"}
      </span>
    </div>
  );
}
