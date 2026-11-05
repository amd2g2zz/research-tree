import { useCallback, useEffect, useRef, useState } from "react";
import { getSocket, rpc, api, onTurnDelta } from "./rpc.js";
import "./styles.css";

interface Project { project_id: string; name: string; status: string;
  vitals: { research_lines: number; latest: { v: number; verdict: string; commit_hash: string } | null; elapsed_ms: number };
  lines: Array<{ task_id: string; role: string; draft: { base_v: number | null } | null }> }
type Kind = "auto" | "preference" | "claim" | "guess" | "branch";
const KINDS: Array<[Kind, string]> = [["auto","自动"],["preference","偏好"],["claim","主张"],["guess","猜测"],["branch","岔路"]];
interface ChatMsg { seq: number; role: string; kind: string; text: string; receipt_json: string | null }

function AppInner() {
  const [tree, setTree] = useState<Project[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [routed, setRouted] = useState(0);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<Kind>("auto");
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [cot, setCot] = useState("");
  const cotBuf = useRef("");
  const [piReady, setPiReady] = useState<boolean | null>(null);
  const [newName, setNewName] = useState("");
  const [showNew, setShowNew] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const push = useCallback((t: string) => {}, []);

  const refresh = useCallback(async () => {
    const d = (await api("/api/tree")) as { projects: Project[] };
    setTree(d.projects);
  }, []);

  const refreshHub = useCallback(async (tid: string) => {
    const w = await getSocket();
    const h = await rpc(w, "chat.history", { task_id: tid });
    setMsgs((h.messages ?? []) as ChatMsg[]);
    const s = await rpc(w, "task.status", { task_id: tid });
    setRouted(Number(s.routed_count ?? 0));
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (taskId) void refreshHub(taskId); }, [taskId, refreshHub]);

  const send = useCallback(async (text: string) => {
    if (!taskId || !text.trim()) return;
    setBusy(true); cotBuf.current = ""; setCot("");
    try {
      if (kind === "auto") {
        onTurnDelta(d => { cotBuf.current += d; setCot(cotBuf.current); });
        const w = (await getSocket()) as WebSocket;
        await rpc(w, "chat.turn", { task_id: taskId, text });
      } else {
        const w = (await getSocket()) as WebSocket;
        await rpc(w, "chat.ingest", { task_id: taskId, text, kind });
      }
      setDraft(""); await refreshHub(taskId);
    } catch (e) { console.error(e); }
    finally { setBusy(false); }
  }, [taskId, kind, refreshHub]);

  const create = useCallback(async (name: string) => {
    if (!name.trim()) return;
    const pid = `p-${Date.now().toString(36)}`;
    const w = (await getSocket()) as WebSocket;
    await rpc(w, "project.create", { project_id: pid, name });
    await rpc(w, "project.registerTask", { project_id: pid, task_id: `${pid}-main`, role: "main" });
    setNewName(""); setShowNew(false); await refresh(); setTaskId(`${pid}-main`);
  }, [refresh]);

  const proj = tree.find(p => p.lines.some(l => l.task_id === taskId)) ?? null;

  return (
    <div className="app">
      <aside className="side">
        <div className="side-head">
          <button className="new-btn" onClick={() => setShowNew(true)}><b>＋</b> 新研究</button>
        </div>
        <nav className="side-list">
          {tree.map(p => (
            <div key={p.project_id} className="proj-group">
              <div className="proj-row" onClick={() => setTaskId(p.lines.find(l => l.role === "main")?.task_id ?? null)}>
                {p.name}
              </div>
              {p.lines.map(l => (
                <div key={l.task_id} className={`task-row ${l.task_id === taskId ? "active" : ""}`} onClick={() => setTaskId(l.task_id)}>
                  <span className="ico">{l.role === "main" ? "◉" : "⑂"}</span> {l.task_id}
                </div>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <div className="pi-status"><span className={`dot ${piReady ? "ok" : "off"}`} /> {piReady === null ? "…" : piReady ? "keyed 就绪" : "未配置 key"}</div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar"><h1>{proj?.name ?? "research-tree"}</h1></header>
        <div className="stream">
          {msgs.map(m =>
            m.role === "user"
              ? <div key={m.seq} className="bubble user">{m.text}</div>
              : m.kind === "reply"
                ? <div key={m.seq} className="agent-msg"><div className="agent-label">rt</div><div className="agent-text">{m.text}</div></div>
                : m.kind === "question"
                  ? <div key={m.seq} className="question-row">❓ {m.text}</div>
                  : m.kind === "recon"
                    ? <details key={m.seq} className="recon-box"><summary>🔎 {m.text.slice(0, 80)}</summary><div>{m.text}</div></details>
                    : <div key={m.seq} className="receipt-row">◉ {m.text}</div>
          )}
          {thinking && <div className="agent-msg typing"><div className="agent-label">rt · 思考中</div><div className="dots"><span/><span/><span/></div>{cot && <pre className="cot-stream">{cot}</pre>}</div>}
          {!msgs.length && !thinking && <div className="empty center">把想法倒进来——研究从对话发起。</div>}
        </div>
        <div className="composer">
          <select value={kind} onChange={e => setKind(e.target.value as Kind)} className="kind-sel">
            {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
          <input value={draft} onChange={e => setDraft(e.target.value)} placeholder="追问、纠正、追加信息……"
            onKeyDown={e => e.key === "Enter" && draft.trim() && void send(draft)} disabled={!taskId} />
          <button className="send-btn" onClick={() => void send(draft)} disabled={!draft.trim() || busy || !taskId}>{busy ? "…" : "↑"}</button>
        </div>
      </main>
      {showNew && (
        <div className="overlay" onClick={() => setShowNew(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>新研究</h3>
            <input autoFocus placeholder="研究主题" value={newName} onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && newName.trim() && void create(newName)} />
            <div className="modal-actions">
              <button onClick={() => setShowNew(false)}>取消</button>
              <button className="primary" onClick={() => void create(newName)} disabled={!newName.trim()}>建立研究</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AppInner;
