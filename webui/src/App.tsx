/** WebUI spike app (issue #632): P0 home + a live research console wired to
 * the backend over WS/REST. The spike drives ONE scripted research round
 * (decomposition fixture lives client-side, labeled 端到端演练); the real
 * dialogue/decomposition pages land in #634/#635. */

import { useCallback, useEffect, useRef, useState } from "react";

interface ProjectCard {
  project_id: string;
  name: string;
  status: string;
}
interface Vitals {
  research_lines: number;
  latest: { v: number; verdict: string; commit_hash: string } | null;
  elapsed_ms: number;
}
interface PiConfig {
  config_path: string;
  present: boolean;
  default_model: string | null;
  models: string[];
  auth_providers: string[];
}
interface LogLine {
  kind: "engine" | "rpc" | "error";
  text: string;
}

const WALK_STEPS = [
  {
    event: "open-draft",
    snapshot: { elements: {}, claims: [], evidence_refs: [], report: {}, deleted_nodes: [] },
    base_v: null,
  },
  {
    event: "attach",
    decomposition_id: "dc-spike",
    decomposition: {
      requirements: [{ text: "deploy on 2C4G fast", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" } }],
      constraints: [{ text: "2C4G is a guess", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" }, hardness: "guessed" }],
      background: [],
      intents: [{ text: "ship fast", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" } }],
      refusals: [],
      difficulties: [{ text: "2C4G memory ceiling", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" }, kill_candidates: ["c-mob"] }],
      claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
    },
    plan: {
      plan_id: "plan-spike",
      stages: [{ id: "s1", title: "recon", claim_ids: [], depends_on: [] }],
      budget: { capMs: 12 * 3600 * 1000 },
      yaw_checks: [
        { slot: "plan-level", mode: "auto" },
        { slot: "problem-level", mode: "human" },
        { slot: "knowledge-level", mode: "auto" },
      ],
    },
  },
  { event: "confirm" },
  { event: "sign" },
  { event: "research-completed" },
];

export function App() {
  const [projects, setProjects] = useState<ProjectCard[]>([]);
  const [vitals, setVitals] = useState<Vitals | null>(null);
  const [piConfig, setPiConfig] = useState<PiConfig | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const [name, setName] = useState("");

  const refresh = useCallback(async () => {
    const res = await fetch("/api/projects");
    setProjects(((await res.json()) as { projects: ProjectCard[] }).projects);
    setPiConfig((await (await fetch("/api/config/pi")).json()) as PiConfig);
  }, []);

  const loadVitals = useCallback(async (projectId: string) => {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/vitals`);
    if (res.ok) {
      setVitals((await res.json()) as Vitals);
    }
  }, []);

  const push = useCallback((kind: LogLine["kind"], text: string) => {
    setLog((prev) => [...prev.slice(-199), { kind, text }]);
  }, []);

  const connect = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => resolve(ws);
      ws.onerror = reject;
    });
  }, []);

  const rpc = useCallback((ws: WebSocket, method: string, params: Record<string, unknown> = {}) => {
    return new Promise<Record<string, unknown>>((resolve, reject) => {
      const id = Date.now() + Math.random();
      const onMessage = (ev: MessageEvent): void => {
        const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        if (msg.id === id) {
          ws.removeEventListener("message", onMessage);
          if (msg.ok === true) {
            resolve(msg.result as Record<string, unknown>);
          } else {
            reject(new Error(String(msg.error)));
          }
        } else if (msg.event === "engine") {
          const line = msg.line as { event_type?: string; seq?: number };
          push("engine", `#${line.seq} ${line.event_type}`);
        }
      };
      ws.addEventListener("message", onMessage);
      ws.send(JSON.stringify({ id, method, params }));
    });
  }, [push]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createProject = async (): Promise<void> => {
    if (name.trim() === "") {
      return;
    }
    const project_id = `p-${Date.now().toString(36)}`;
    const ws = socketRef.current ?? (socketRef.current = await connect());
    try {
      await rpc(ws, "project.create", { project_id, name: name.trim() });
      await rpc(ws, "project.registerTask", { project_id, task_id: `${project_id}-main`, role: "main" });
      push("rpc", `项目 ${name.trim()} 已创建（主线 ${project_id}-main）`);
      setName("");
      await refresh();
      await loadVitals(project_id);
    } catch (error) {
      push("error", String(error));
    }
  };

  const runWalk = async (): Promise<void> => {
    setRunning(true);
    try {
      const ws = socketRef.current ?? (socketRef.current = await connect());
      const projectId = projects[0]?.project_id;
      if (projectId === undefined) {
        throw new Error("先建一个项目");
      }
      push("rpc", "端到端演练开始：分解 → 签署 → 研究 → 冻结提交");
      const result = await rpc(ws, "research.launch", {
        task_id: `${projectId}-main`,
        pre_signed: { verdict: "GO", summary: "webui spike 演练提交" },
        steps: WALK_STEPS,
      });
      push("rpc", `演练完成：outcome=${String(result.outcome)} events=${String(result.events)}`);
      await refresh();
      await loadVitals(projectId);
    } catch (error) {
      push("error", String(error));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>research-tree</h1>
        <div className="pi-config">
          {piConfig === null
            ? "pi 配置读取中…"
            : piConfig.present
              ? `pi 同源配置：默认模型 ${piConfig.default_model ?? "未设置"} · provider ${piConfig.auth_providers.join(", ") || "无"}`
              : "未找到 pi 配置（~/.pi/agent）"}
        </div>
      </header>
      <main>
        <section className="card">
          <h2>项目</h2>
          <div className="row">
            <input
              placeholder="新项目名称（一个项目 = 一个研究主题）"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && name.trim() !== "" && void createProject()}
            />
            <button onClick={() => void createProject()} disabled={name.trim() === ""}>
              建项目
            </button>
          </div>
          <ul className="projects">
            {projects.map((p) => (
              <li key={p.project_id} onClick={() => void loadVitals(p.project_id)}>
                <strong>{p.name}</strong> <span className={`status ${p.status}`}>{p.status}</span>
              </li>
            ))}
            {projects.length === 0 && <li className="empty">还没有项目——建一个开始研究</li>}
          </ul>
        </section>
        <section className="card">
          <h2>三体征</h2>
          {vitals === null ? (
            <p className="empty">点左侧项目查看</p>
          ) : (
            <div className="vitals">
              <div>研究线：{vitals.research_lines}</div>
              <div>
                主分支最新：{" "}
                {vitals.latest === null ? (
                  "未提交"
                ) : (
                  <code>
                    v{vitals.latest.v} · {vitals.latest.verdict} · {vitals.latest.commit_hash.slice(0, 12)}
                  </code>
                )}
              </div>
              <div>已用时间：{Math.round(vitals.elapsed_ms / 1000)}s</div>
            </div>
          )}
          <button onClick={() => void runWalk()} disabled={running || projects.length === 0}>
            {running ? "研究推进中…" : "端到端演练（分解→签署→研究→冻结提交）"}
          </button>
          <p className="hint">演练走 #579 headless 全链路；真实对话/分解页在 #634/#635 落地。</p>
        </section>
        <section className="card console">
          <h2>引擎事件流</h2>
          <div className="log">
            {log.map((line, i) => (
              <div key={i} className={`line ${line.kind}`}>
                {line.text}
              </div>
            ))}
            {log.length === 0 && <div className="empty">等待事件…</div>}
          </div>
        </section>
      </main>
    </div>
  );
}
