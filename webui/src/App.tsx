/** WebUI P0/P1 (issue #633): home = default landing with the card wall
 * (create / list-with-vitals / archive / delete-archived-only — engine red
 * lines surfaced verbatim) and the P1 sidebar tree (project → research lines
 * main/fork → version nodes with fork markers + the draft row
 * 未冻结·不可跟踪). Data comes from /api/tree assembled over #571/#548. */

import { useCallback, useEffect, useRef, useState } from "react";

interface ProjectCard {
  project_id: string;
  name: string;
  description: string;
  status: string;
  attachments: Array<{ id: string; kind: string; label: string }>;
}
interface VersionNode {
  v: number;
  verdict: string;
  commit_hash: string;
  summary: string;
  forked: boolean;
}
interface LineNode {
  task_id: string;
  role: "main" | "fork";
  latest: { v: number; verdict: string; commit_hash: string; summary: string } | null;
  versions: VersionNode[];
  draft: { base_v: number | null; updated_at: string } | null;
}
interface TreeNode extends ProjectCard {
  vitals: {
    research_lines: number;
    latest: { v: number; verdict: string; commit_hash: string } | null;
    elapsed_ms: number;
  };
  lines: LineNode[];
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
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [piConfig, setPiConfig] = useState<{ present: boolean; default_model: string | null; auth_providers: string[] } | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const [name, setName] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  const push = useCallback((kind: LogLine["kind"], text: string) => {
    setLog((prev) => [...prev.slice(-199), { kind, text }]);
  }, []);

  const refreshTree = useCallback(async () => {
    const res = await fetch("/api/tree");
    const projects = ((await res.json()) as { projects: TreeNode[] }).projects;
    setTree(projects);
    setSelected((current) => current ?? projects.find((p) => p.status === "active")?.project_id ?? null);
  }, []);

  useEffect(() => {
    void refreshTree();
    void fetch("/api/config/pi")
      .then((r) => r.json())
      .then((c) => setPiConfig(c as never));
  }, [refreshTree]);

  const connect = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => resolve(ws);
      ws.onerror = reject;
    });
  }, []);

  const rpc = useCallback(
    (ws: WebSocket, method: string, params: Record<string, unknown> = {}) => {
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
    },
    [push],
  );

  const getSocket = useCallback(async (): Promise<WebSocket> => {
    if (socketRef.current === null || socketRef.current.readyState > 1) {
      socketRef.current = await connect();
    }
    return socketRef.current;
  }, [connect]);

  const createProject = async (): Promise<void> => {
    if (name.trim() === "") {
      return;
    }
    try {
      const project_id = `p-${Date.now().toString(36)}`;
      const ws = await getSocket();
      await rpc(ws, "project.create", { project_id, name: name.trim() });
      await rpc(ws, "project.registerTask", { project_id, task_id: `${project_id}-main`, role: "main" });
      push("rpc", `项目已创建，落其首页（主线 ${project_id}-main）`);
      setName("");
      await refreshTree();
      setSelected(project_id);
    } catch (error) {
      push("error", String(error));
    }
  };

  const manage = async (projectId: string, action: "archive" | "delete"): Promise<void> => {
    try {
      await rpc(await getSocket(), `project.${action}`, { project_id: projectId });
      push("rpc", `project.${action} ok`);
      if (selected === projectId) {
        setSelected(null);
      }
      await refreshTree();
    } catch (error) {
      push("error", String(error)); // engine red line surfaced verbatim
    }
  };

  const runWalk = async (): Promise<void> => {
    setRunning(true);
    try {
      const project = tree.find((p) => p.project_id === selected);
      if (project === undefined) {
        throw new Error("先建一个项目");
      }
      push("rpc", "端到端演练开始：分解 → 签署 → 研究 → 冻结提交");
      const result = await rpc(await getSocket(), "research.launch", {
        task_id: project.lines.find((l) => l.role === "main")?.task_id ?? `${project.project_id}-main`,
        pre_signed: { verdict: "GO", summary: "webui 演练提交" },
        steps: WALK_STEPS,
      });
      push("rpc", `演练完成：outcome=${String(result.outcome)} events=${String(result.events)}`);
      await refreshTree();
    } catch (error) {
      push("error", String(error));
    } finally {
      setRunning(false);
    }
  };

  const selectedProject = tree.find((p) => p.project_id === selected) ?? null;

  return (
    <div className="app">
      <header>
        <h1 onClick={() => setSelected(tree.find((p) => p.status === "active")?.project_id ?? null)}>research-tree</h1>
        <div className="pi-config">
          {piConfig === null
            ? "pi 配置读取中…"
            : piConfig.present
              ? `pi 同源配置：默认模型 ${piConfig.default_model ?? "未设置"} · provider ${piConfig.auth_providers.join(", ") || "无"}`
              : "未找到 pi 配置（~/.pi/agent）"}
        </div>
      </header>
      <div className="layout">
        {/* ---------------- P1 侧栏研究树 ---------------- */}
        <nav className="sidebar card">
          <h2>研究树</h2>
          {tree.map((project) => (
            <div key={project.project_id} className="tree-project">
              <div className={`tree-row project ${project.status}`} onClick={() => setSelected(project.project_id)}>
                📁 {project.name}
                <span className={`status ${project.status}`}>{project.status}</span>
              </div>
              {project.lines.map((line) => (
                <div key={line.task_id} className="tree-line">
                  <div className={`tree-row line-node ${line.role}`}>
                    {line.role === "main" ? "●" : "⑂"} {line.task_id}
                  </div>
                  {line.draft !== null && <div className="tree-row draft">✎ 草稿（未冻结·不可跟踪）</div>}
                  {line.versions.map((v) => (
                    <div key={v.v} className="tree-row version">
                      v{v.v} · {v.verdict} · <code>{v.commit_hash.slice(0, 8)}</code>
                      {v.forked && <span className="fork-mark">⑂ 已分叉</span>}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ))}
        </nav>
        <main>
          {/* ---------------- P0 项目首页 ---------------- */}
          <section className="card">
            <h2>项目首页（应用默认落点）</h2>
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
            {selectedProject === null ? (
              <p className="empty">从研究树选择项目</p>
            ) : (
              <>
                <div className="card-head">
                  <strong>{selectedProject.name}</strong>
                  {selectedProject.attachments.map((a) => (
                    <span key={a.id} className="chip">
                      {a.label}
                    </span>
                  ))}
                  <span className="spacer" />
                  {selectedProject.status === "active" ? (
                    <button className="ghost" onClick={() => void manage(selectedProject.project_id, "archive")}>
                      归档
                    </button>
                  ) : (
                    <button className="ghost danger" onClick={() => void manage(selectedProject.project_id, "delete")}>
                      删除（仅归档可删）
                    </button>
                  )}
                </div>
                <div className="vitals">
                  <div>研究线：{selectedProject.vitals.research_lines}</div>
                  <div>
                    主分支最新：{" "}
                    {selectedProject.vitals.latest === null ? (
                      "未提交"
                    ) : (
                      <code>
                        v{selectedProject.vitals.latest.v} · {selectedProject.vitals.latest.verdict} ·{" "}
                        {selectedProject.vitals.latest.commit_hash.slice(0, 12)}
                      </code>
                    )}
                  </div>
                  <div>已用时间：{Math.round(selectedProject.vitals.elapsed_ms / 1000)}s</div>
                </div>
                {selectedProject.vitals.latest !== null && <button className="ghost">查看最新报告（快照视图 #637 落地）</button>}
                <button onClick={() => void runWalk()} disabled={running || selectedProject.status !== "active"}>
                  {running ? "研究推进中…" : "端到端演练（分解→签署→研究→冻结提交）"}
                </button>
                <p className="hint">演练走 #579 headless 全链路；真实对话/分解页在 #634/#635 落地。</p>
              </>
            )}
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
    </div>
  );
}
