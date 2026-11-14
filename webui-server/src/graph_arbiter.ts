/** 图仲裁 subagent（issue #715，用户裁定：图是多阶段有向无环图，由专门的
 * subagent 仲裁动态生长与预计算）。

职责边界：
- **预计算**：确认导图时，从 mindmap 分支仲裁出初始任务图（节点+依赖边）
- **动态生长**：每个 wave（一组就绪节点并行执行完毕）结束后，仲裁员基于
  已完成节点的发现决定：追加子任务节点（含依赖边）/ 宣布图完成
- **机械保障**（非 LLM）：Kahn 环检测拒绝成环边、节点总数/每波/深度上限、
  标题去重——仲裁产物全部经过 validateStages 才能入库

LLM 失败 → 返回 null，调用方落级到机械种子（每分支一个探索节点），
图仍闭合（汇总节点诚实收尾）——图永远是有向无环且可终止的。
*/

import { extractJsonObject } from "./mindmap.js";

export interface ArbiterNode {
  title: string;
  purpose?: string;
  /** 期望信息增益先验（0~1）——执行后与实测后验对比，驱动分支阻尼 */
  expectedGain?: number;
  /** 依赖的节点标题或 id（校验器解析为 stage_id；成环/未知依赖被丢弃） */
  after?: string[];
}

export interface ArbiterResult {
  /** 图完成——不再生长，执行器注册汇总节点 */
  done: boolean;
  nodes: ArbiterNode[];
  note?: string;
}

export interface ArbiterDeps {
  piRunner?: (command: string, prompt: string) => string | Promise<string>;
  piCommand: () => string | null;
  piTimeoutMs?: number;
}

export interface ArbiterNodeInput {
  stage_id: string;
  title: string;
  status: string;
  findings: string | null;
}

/** 仲裁员 prompt（图状态 + 已完成发现 + 导图分支 → 图生长决策）。

#729 缓存前缀律：**稳定样板（角色+规则+输出格式）必须全部在 prompt
前部**，逐 wave 变化的部分（wave 号+节点状态）压到最后——否则 wave 号
把规则段推出共享前缀，跨 wave 调用的缓存命中率崩塌。 */
export function buildArbiterPrompt(
  question: string,
  branches: string[],
  nodes: ArbiterNodeInput[],
  wave: number,
): string {
  const nodeLines = nodes
    .map(
      (n) =>
        `- [${n.stage_id}] ${n.title}（${n.status}）${
          n.findings !== null ? `\n  发现：${n.findings.slice(0, 400)}` : ""
        }`,
    )
    .join("\n");
  return (
    "你是 DAG 图仲裁员，负责一个调研任务图的**动态生长**——用期望信息增益决定图往哪里长。\n" +
    "规则：\n" +
    "1. 图必须**有向无环**：新节点的 after 只能引用本次输入列出的节点 id；\n" +
    "2. 每个新节点 title 带类型前缀（深挖｜/分析｜/验证｜），purpose 一句话说明它回答什么；\n" +
    "3. **expectedGain（0~1）= 该节点对回答整体问题的边际信息增益先验估计**：发现里未覆盖但关键的子问题给高分；与已有发现重复、或只是换措辞的子问题给低分——执行器会实测后验增益并压低后续分支的估值，虚报会被收益递减自然抑制；\n" +
    "4. 当剩余的空白都已被覆盖、或新节点期望增益都很低（收益递减）→ done=true；\n" +
    "5. 不得编造发现里没有的信息。\n" +
    '只输出 JSON：{"done":false,"note":"一句话理由","nodes":[{"title":"深挖｜...","purpose":"...","expectedGain":0.7,"after":["<节点id>"]}]}\n' +
    "\n【本次仲裁输入】\n" +
    "整体研究问题：" +
    question +
    "\n导图初始分支：" +
    branches.join("；") +
    "\n当前图状态（wave " +
    wave +
    "，damping 为当前分支阻尼系数——历史收益递减的分支新节点会被压值）：\n" +
    nodeLines +
    "\n"
  );
}

/** 调用仲裁 subagent。LLM 失败/输出不可解析 → null（调用方机械兜底）。 */
export async function arbiterPlan(
  deps: ArbiterDeps,
  question: string,
  branches: string[],
  nodes: ArbiterNodeInput[],
  wave: number,
): Promise<ArbiterResult | null> {
  const command = deps.piCommand();
  if (command === null) return null;
  const prompt = buildArbiterPrompt(question, branches, nodes, wave);
  try {
    const stdout =
      deps.piRunner !== undefined
        ? await deps.piRunner(command, prompt)
        : await import("./pi-run.js").then((m) =>
            m.runPi(command, prompt, deps.piTimeoutMs ?? 300_000, ["-nt", "-ne", "--no-session", "--no-skills"]),
          );
    const json = extractJsonObject(stdout);
    if (json === null) return null;
    const parsed = JSON.parse(json) as {
      done?: boolean;
      note?: string;
      nodes?: Array<{
        title?: string;
        purpose?: string;
        expectedGain?: number;
        after?: string[];
      }>;
    };
    const nodes = Array.isArray(parsed.nodes)
      ? parsed.nodes
          .filter((n) => typeof n.title === "string" && n.title.trim() !== "")
          .map((n) => ({
            title: String(n.title),
            purpose: typeof n.purpose === "string" ? n.purpose : undefined,
            expectedGain: typeof n.expectedGain === "number" ? Math.min(Math.max(n.expectedGain, 0), 1) : 0.6,
            after: Array.isArray(n.after) ? (n.after.filter((a) => typeof a === "string") as string[]) : [],
          }))
      : [];
    return {
      done: parsed.done === true,
      note: typeof parsed.note === "string" ? parsed.note : undefined,
      nodes,
    };
  } catch {
    return null;
  }
}

/** Kahn 环检测：edges 无环返回 true。 */
export function isAcyclic(nodeIds: string[], edges: Array<[string, string]>): boolean {
  const deps = new Map<string, string[]>();
  for (const id of nodeIds) deps.set(id, []);
  for (const [from, to] of edges) {
    if (deps.has(from) && deps.has(to)) deps.get(from)!.push(to);
  }
  let remaining = nodeIds.length;
  let progress = true;
  const done = new Set<string>();
  while (progress && remaining > 0) {
    progress = false;
    for (const id of nodeIds) {
      if (done.has(id)) continue;
      const ds = deps.get(id)!;
      if (ds.every((d) => done.has(d))) {
        done.add(id);
        remaining -= 1;
        progress = true;
      }
    }
  }
  return remaining === 0;
}

export interface ValidatedNode {
  stage_id: string;
  title: string;
  claim_ids: string[];
  depends_on: string[];
}

/** 仲裁产物校验与并入（机械规则）：标题去重、after 解析为已存在节点 id、
 * Kahn 环检测丢弃成环依赖、节点总数上限。返回可注册的新阶段。 */
export function validateProposed(
  existing: Array<{ stage_id: string; title: string }>,
  proposed: ArbiterNode[],
  taskId: string,
  wave: number,
  damping = 1,
  eps = 0.08,
  maxNodes = 64,
): ValidatedNode[] {
  const titleToId = new Map<string, string>();
  for (const e of existing) titleToId.set(e.title, e.stage_id);
  const out: ValidatedNode[] = [];
  const takenTitles = new Set(existing.map((e) => e.title));
  // OOM 硬护栏（LLM 调用成本）——增长本身由增益阻尼抑制，不写死数量
  let budget = maxNodes - existing.length;
  for (const node of proposed) {
    if (budget <= 0) break;
    const estGain = (node.expectedGain ?? 0.6) * damping;
    if (estGain < eps) continue; // 增益被阻尼压到阈值以下——抑制（收益递减）
    const title = node.title.trim();
    if (title === "" || takenTitles.has(title)) continue;
    const id = `${taskId}/g${wave}-${out.length + 1}-${Math.abs(
      [...title].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) | 0, 0),
    )}`;
    titleToId.set(title, id);
    takenTitles.add(title);
    const deps: string[] = [];
    for (const after of node.after ?? []) {
      const depId = titleToId.get(after) ?? (/^(p-|t-)/.test(after) ? after : undefined);
      if (depId !== undefined && depId !== id && !deps.includes(depId)) deps.push(depId);
    }
    out.push({
      stage_id: id,
      title,
      claim_ids: [],
      depends_on: deps,
    });
    budget -= 1;
  }
  // 环检测：把现有边 + 新边一起做 Kahn；成环的边逐条丢弃再验
  const nodeIds = [...existing.map((e) => e.stage_id), ...out.map((o) => o.stage_id)];
  const edges: Array<[string, string]> = [];
  const depEdges = new Map<string, string[]>();
  for (const e of existing) depEdges.set(e.stage_id, []);
  const edgesOfNew = new Map<string, string[]>();
  for (const o of out) edgesOfNew.set(o.stage_id, [...o.depends_on]);
  for (const id of nodeIds) {
    if (!depEdges.has(id)) depEdges.set(id, edgesOfNew.get(id) ?? []);
  }
  const tryEdges = (): Array<[string, string]> => {
    const all: Array<[string, string]> = [];
    for (const [id, ds] of depEdges) for (const d of ds) all.push([id, d]);
    return all;
  };
  let edgesNow = tryEdges();
  while (!isAcyclic(nodeIds, edgesNow)) {
    // 丢弃一条指向新节点的边（仲裁产物的依赖不可信时优先裁边保节点）
    let dropped = false;
    for (const o of out) {
      const ds = edgesOfNew.get(o.stage_id) ?? [];
      if (ds.length > 0) {
        const removed = ds.pop()!;
        edgesNow = tryEdges();
        if (isAcyclic(nodeIds, edgesNow)) {
          dropped = true;
          break;
        }
        ds.push(removed); // 还不是这条，恢复
      }
    }
    if (!dropped) break;
  }
  void edges;
  return out;
}
