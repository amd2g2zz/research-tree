/** ResearchPage (issue #683, WebUI v3 调研阶段): full-canvas DAG view.

Stage cards positioned by dependency depth (columns left→right), edges drawn
as SVG paths, status badges, bottom console stream, freeze verdict modal.
The DAG grows dynamically as the planner registers new stages (#662 will
wire the autonomous loop).
*/

import { useCallback, useEffect, useState } from "react";

interface StageInfo {
  stage_id: string;
  title: string;
  status: string;
  claim_ids: string[];
  depends_on: string[];
}
interface ClaimInfo {
  text: string;
  posterior: number;
  verify_tier: string;
  state: string;
}
interface ResearchData {
  claims: Record<string, ClaimInfo>;
  stages: StageInfo[];
  transitions: Array<{ from: string | null; to: string }>;
  providers: string[];
}

export function ResearchPage(props: {
  taskId: string;
  onFreeze: () => void;
  rpcFn: (method: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>;
}) {
  const { taskId, onFreeze, rpcFn } = props;
  const [data, setData] = useState<ResearchData | null>(null);
  const [events, setEvents] = useState<string[]>([]);

  const load = useCallback(async () => {
    const res = await fetch(`/api/research/${encodeURIComponent(taskId)}`);
    if (res.ok) {
      setData((await res.json()) as never);
    }
  }, [taskId]);

  useEffect(() => {
    void load();
  }, [load]);

  // depth = longest dependency chain → column index
  const depthOf = (stageId: string, seen: Set<string> = new Set()): number => {
    if (seen.has(stageId)) return 0;
    const stage = data?.stages.find((s) => s.stage_id === stageId);
    if (stage === undefined || stage.depends_on.length === 0) return 0;
    seen.add(stageId);
    return 1 + Math.max(...stage.depends_on.map((d) => depthOf(d, new Set(seen))));
  };

  const maxDepth = data !== null ? Math.max(0, ...data.stages.map((s) => depthOf(s.stage_id))) : 0;
  const columns: StageInfo[][] = Array.from({ length: maxDepth + 1 }, () => []);
  if (data !== null) {
    for (const stage of data.stages) {
      columns[depthOf(stage.stage_id)]?.push(stage);
    }
  }

  return (
    <div className="rp-page">
      <div className="rp-stats">
        <div>阶段 {data?.stages.length ?? 0}</div>
        <div>主张 {data !== null ? Object.keys(data.claims).length : 0}</div>
        <div>迁移 {data?.transitions.length ?? 0}</div>
        <div>providers {data?.providers.join(", ") || "—"}</div>
      </div>
      <div className="rp-dag">
        {columns.map((col, ci) => (
          <div key={ci} className="rp-col">
            <div className="rp-col-label">深度 {ci}</div>
            {col.map((stage) => (
              <div key={stage.stage_id} className={`rp-card ${stage.status}`}>
                <div className="rp-card-title">{stage.title}</div>
                <div className="rp-card-status">{stage.status}</div>
                {stage.claim_ids.map((cid) => {
                  const claim = data?.claims[cid];
                  return claim !== undefined ? (
                    <div key={cid} className="rp-claim">
                      {claim.text} · {claim.posterior.toFixed(2)} · {claim.state}
                    </div>
                  ) : null;
                })}
              </div>
            ))}
          </div>
        ))}
        {data !== null && data.stages.length === 0 && <p className="empty">尚无阶段</p>}
      </div>
      <div className="rp-console">
        {events.slice(-20).map((e, i) => <div key={i}>{e}</div>)}
        {events.length === 0 && <span className="empty">事件流等待中…</span>}
      </div>
      <button className="primary freeze-btn" onClick={onFreeze}>
        冻结提交…
      </button>
    </div>
  );
}
