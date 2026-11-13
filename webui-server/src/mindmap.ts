/** Mindmap tree (issue #683, WebUI v3 确认阶段 full-canvas page).

The chat produces a messy transcript; the mindmap turns it into a
STRUCTURED tree the user confirms before research:

- root = the core question distilled from the conversation
- depth-1 branches: at least 限制条件 / 任务背景 / 调研目标 (more allowed)
- each branch decomposes up to 5 levels
- every node carries a provenance quote mapped back to the transcript
  (溯源律 — unmapped quotes keep no provenance and are flagged)

Storage: migration v9 `mindmaps` (task_id PK, tree_json, status
draft|confirmed). Editing is draft-only; confirming freezes the tree and
mechanically derives the research stages (each LEAF node becomes a stage).
*/

export interface MindNode {
  id: string;
  text: string;
  /** branch identity for depth-1 nodes — survives editor renaming */
  branch?: string;
  /** provenance quote mapped back to the transcript (溯源律) */
  quote?: string;
  children: MindNode[];
}

export interface MindTree {
  root: MindNode;
}

export const MAX_DEPTH = 5;
export const REQUIRED_BRANCHES = ["限制条件", "任务背景", "调研目标"] as const;

export function mindmapPrompt(messages: Array<{ seq: number; role: string; text: string }>): string {
  const transcript = messages
    .filter((m) => m.role === "user" || m.role === "rt")
    .map((m) => `[${m.seq}][${m.role}] ${m.text}`)
    .join("\n");
  return (
    "你是研究结构师。把下面的对话整理成一张研究策略思维导图 JSON（只输出 JSON）：\n" +
    '{"root":{"text":"核心问题一句话","children":' +
    '[{"text":"方向概括","children":[{"text":"命题概括","quote":"对话原话片段"}]}]}}\n' +
    "规则（溯源律——导图是对话内容的抽取与总结，不是你的创作，违者整份输出作废）：\n" +
    "1. root = 从对话提炼的核心问题（一句话）。\n" +
    "2. 节点 text = 你对对话内容的**提炼总结**：用自己的话概括语义（分组节点概括研究方向，叶子节点是可验证的具体命题），不要照抄整句原话。\n" +
    "3. 每个叶子节点必须携带 quote 字段 = 支撑该命题的对话原句**逐字片段**；quote 会被逐字回查，对不上的节点整节点丢弃。\n" +
    "4. 中间分组节点可以不带 quote（纯结构），但其下必须存在带 quote 的叶子。\n" +
    "5. 只总结对话中说过的内容：对话没提到的类别、命题、数字、策略一律不得编造，也不得为凑结构填模板分支——宁可分支缺失。\n" +
    '6. 对话信息不足以形成任何带溯源的分支时，输出 {"root":{"text":"...","children":[]}}。\n' +
    "7. 总深度 ≤5 层。\n\n对话：\n" +
    transcript
  );
}

export interface ParsedMindmap {
  tree: MindTree;
  dropped: number;
  depth: number;
}

/** First balanced JSON object in `text` (string-aware brace-depth scan).
 * Models wrap the JSON in fences and append prose — a greedy `\{[\s\S]*\}`
 * match swallows those and fails JSON.parse (issue #690 e2e). */
export function extractJsonObject(text: string): string | null {
  const start = text.indexOf("{");
  if (start === -1) return null;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

/** Parse the model's tree JSON, map quotes back to the transcript, enforce ≤5 depth. */
export function parseMindmap(
  stdout: string,
  messages: Array<{ seq: number; role: string; text: string }>,
): ParsedMindmap {
  const match = extractJsonObject(stdout);
  if (match === null) {
    throw new Error("mindmap returned no JSON object");
  }
  let raw: { root?: { text?: string; children?: unknown[] } };
  try {
    raw = JSON.parse(match) as {
      root?: { text?: string; children?: unknown[] };
    };
  } catch {
    throw new Error(`mindmap returned malformed JSON: ${match.slice(0, 60)}`);
  }
  if (raw.root === undefined || typeof raw.root.text !== "string" || raw.root.text === "") {
    throw new Error("mindmap returned no root");
  }
  let dropped = 0;

  const build = (nodes: unknown[], depth: number): MindNode[] =>
    nodes
      .filter(
        (n): n is Record<string, unknown> =>
          typeof n === "object" && n !== null && typeof (n as Record<string, unknown>).text === "string",
      )
      .map((n) => {
        const quote = typeof n.quote === "string" && n.quote !== "" ? n.quote : undefined;
        let provenance: string | undefined;
        if (quote !== undefined) {
          const hit = messages.find((m) => m.role === "user" && m.text.includes(quote));
          provenance = hit !== undefined ? quote : undefined;
        }
        const kids = depth >= MAX_DEPTH ? [] : Array.isArray(n.children) ? build(n.children, depth + 1) : [];
        return {
          id: `n${depth}-${Math.abs(hash((n.text as string) + depth))}`,
          text: n.text as string,
          quote: provenance,
          children: kids,
        };
      });

  // 溯源律剪枝（#694 用户裁定：导图是从 context 抽取的，不能瞎编）：
  // 节点可保留当且仅当 (a) 自带映射成功的 quote，或 (b) 其下存在可溯源后代
  // （纯分组）。其余 = 模型编造，剪掉并如实计数。
  const prune = (node: MindNode): MindNode | null => {
    const tracedKids = node.children.map(prune).filter((c): c is MindNode => c !== null);
    if (node.quote !== undefined) {
      return {
        id: node.id,
        text: node.text,
        quote: node.quote,
        children: tracedKids,
      };
    }
    if (tracedKids.length > 0) {
      return { id: node.id, text: node.text, children: tracedKids };
    }
    dropped += 1;
    return null;
  };

  const rootChildren = build(Array.isArray(raw.root.children) ? raw.root.children : [], 1)
    .map(prune)
    .filter((c): c is MindNode => c !== null);
  if (rootChildren.length === 0) {
    // fail-closed：空壳导图比编造更有害——明确告诉用户上下文不够
    throw new Error(
      "思维导图抽取 fail-closed：所有候选节点均无法溯源（对话中没有可抽取的内容），拒绝输出编造导图——请继续补充对话信息后再生成",
    );
  }
  // tag depth-1 nodes with branch identity (survives renaming in the editor)
  const branchNames = ["限制条件", "任务背景", "调研目标", "拒绝点", "难点"];
  for (const [i, child] of rootChildren.entries()) {
    const match = branchNames.find((bn) => child.text.includes(bn) || bn.includes(child.text));
    if (match !== undefined) {
      child.branch = match;
    }
  }
  const depth = treeDepth(rootChildren);
  return {
    tree: { root: { id: "root", text: raw.root.text, children: rootChildren } },
    dropped,
    depth,
  };
}

function treeDepth(nodes: MindNode[]): number {
  if (nodes.length === 0) {
    return 1;
  }
  return 1 + Math.max(...nodes.map((c) => treeDepth(c.children)));
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return h;
}

/** Seed graph from the confirmed tree (graph engineering, #715): the mindmap
 * does NOT flatten into a fixed phase template — each depth-1 BRANCH becomes
 * one **explore** node (探索｜branch text). The graph then GROWS at runtime:
 * the planner (see research_worker.ts planNext) spawns subtask nodes from
 * each node's findings, and the final 汇总 node is auto-closed once every
 * branch node is complete. 导图 = 调研的种子，不是固定流程模板。 */
export function seedGraphFromTree(tree: MindTree): Array<{
  id: string;
  title: string;
  claim_ids: string[];
  depends_on: string[];
  kind: "explore";
}> {
  const leavesOf = (node: MindNode): string[] =>
    node.children.length === 0 ? [node.id] : node.children.flatMap(leavesOf);
  return tree.root.children.map((branch: MindNode) => ({
    id: `g-${branch.id}`,
    title: `探索｜${branch.text}`,
    claim_ids: leavesOf(branch),
    depends_on: [] as string[],
    kind: "explore" as const,
  }));
}

/** 机械计划保留旧名作别名（server 引用兼容；语义已变为种子图）。 */
export const mechanicalPlan = seedGraphFromTree;

/** In-place tree edit operations (draft only — caller enforces). */
export function editNode(
  tree: MindTree,
  op: {
    action: "rename" | "addChild" | "delete";
    nodeId: string;
    text?: string;
  },
): boolean {
  const visit = (node: MindNode): { parent: MindNode | null; node: MindNode } | null => {
    for (const child of node.children) {
      if (child.id === op.nodeId) {
        return { parent: node, node: child };
      }
      const hit = visit(child);
      if (hit !== null) {
        return hit;
      }
    }
    return null;
  };
  if (op.nodeId === tree.root.id) {
    if (op.action === "rename" && op.text !== undefined) {
      tree.root.text = op.text;
      return true;
    }
    return false; // root cannot be deleted
  }
  const hit = visit(tree.root);
  if (hit === null) {
    return false;
  }
  if (op.action === "rename" && op.text !== undefined) {
    hit.node.text = op.text;
    return true; // branch identity is preserved (rename changes display text only)
  }
  if (op.action === "addChild") {
    hit.node.children.push({
      id: `n-${Date.now().toString(36)}-${Math.abs(hash(hit.node.id + (op.text ?? "")))}`,
      text: op.text ?? "",
      children: [],
    });
    return true;
  }
  if (op.action === "delete") {
    hit.parent!.children = hit.parent!.children.filter((c) => c.id !== op.nodeId);
    return true;
  }
  return false;
}
