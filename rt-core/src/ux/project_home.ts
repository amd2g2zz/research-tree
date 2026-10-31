/** Project home & card wall (issue #571, docs 03 P0).

项目首页是应用默认落点：opening the app / reset / new project all land on the
default project's overview. The model owns the P0 elements and rules over the
v5 `projects` / `project_tasks` tables and the version store:

- **Three vitals**: research-line count / main-branch latest version+verdict+
  hash / main-line elapsed.
- **Research-line list**: main + forks, each with its latest commit summary.
- **Card wall management**: create / list (vitals thumbnail) / archive
  (read-only, listed at the tree bottom) / delete (**archived only**).
- **Default projection** is always the main branch's latest version (A7
  rule 5) — a fork's newer commits never hijack the home view.
- **Multi-project isolation**: every query is scoped by project_id; zero
  cross-talk between parallel projects.
*/

import type { LedgerStore } from "../store/ledger.js";
import type { VersionStore } from "../versions/store.js";

export interface Attachment {
  id: string;
  kind: string;
  label: string;
}

export interface ProjectCard {
  project_id: string;
  name: string;
  description: string;
  status: "active" | "archived";
  attachments: Attachment[];
  created_at: string;
}

export interface ResearchLine {
  task_id: string;
  role: "main" | "fork";
  latest: { v: number; verdict: string; commit_hash: string; summary: string } | null;
}

export interface ProjectVitals {
  research_lines: number;
  latest: { v: number; verdict: string; commit_hash: string } | null;
  elapsed_ms: number;
}

export class ProjectHomeError extends Error {}

interface ProjectRow {
  project_id: string;
  name: string;
  description: string;
  status: string;
  attachments: string;
  created_at: string;
}

interface TaskRow {
  task_id: string;
  project_id: string;
  role: string;
  created_at: string;
}

function parseAttachments(json: string): Attachment[] {
  try {
    const parsed = JSON.parse(json) as unknown;
    return Array.isArray(parsed) ? (parsed as Attachment[]) : [];
  } catch {
    return [];
  }
}

export class ProjectHomeModel {
  constructor(
    private readonly ledger: LedgerStore,
    private readonly versions: VersionStore,
  ) {}

  createProject(projectId: string, spec: { name: string; description?: string; attachments?: Attachment[] }): ProjectCard {
    const existing = this.get(projectId);
    if (existing) {
      throw new ProjectHomeError(`project already exists: ${projectId}`);
    }
    this.ledger.connection
      .prepare(
        "INSERT INTO projects (project_id, name, description, status, attachments, created_at) VALUES (?, ?, ?, 'active', ?, ?)",
      )
      .run(projectId, spec.name, spec.description ?? "", JSON.stringify(spec.attachments ?? []), new Date().toISOString());
    return this.get(projectId)!;
  }

  registerTask(projectId: string, taskId: string, role: "main" | "fork"): void {
    const project = this.get(projectId);
    if (!project) {
      throw new ProjectHomeError(`unknown project: ${projectId}`);
    }
    if (project.status === "archived") {
      throw new ProjectHomeError(`project is archived and read-only: ${projectId}`);
    }
    if (role === "main") {
      const existingMain = this.ledger.connection
        .prepare("SELECT task_id FROM project_tasks WHERE project_id = ? AND role = 'main' LIMIT 1")
        .get(projectId) as { task_id: string } | undefined;
      if (existingMain !== undefined) {
        throw new ProjectHomeError(`project already has a main line: ${existingMain.task_id}`);
      }
    }
    this.ledger.connection
      .prepare("INSERT INTO project_tasks (task_id, project_id, role, created_at) VALUES (?, ?, ?, ?)")
      .run(taskId, projectId, role, new Date().toISOString());
  }

  /** The three vitals (研究线数 / 主分支最新版本+裁决+hash / 主线已用时间). */
  vitals(projectId: string): ProjectVitals {
    const lines = this.listLines(projectId);
    const main = lines.find((line) => line.role === "main");
    const latest = main?.latest ?? null;
    const taskRow = this.ledger.connection
      .prepare("SELECT created_at FROM project_tasks WHERE project_id = ? AND role = 'main' LIMIT 1")
      .get(projectId) as { created_at: string } | undefined;
    const elapsedMs = taskRow !== undefined ? Date.now() - new Date(taskRow.created_at).getTime() : 0;
    return {
      research_lines: lines.length,
      latest: latest !== null ? { v: latest.v, verdict: latest.verdict, commit_hash: latest.commit_hash } : null,
      elapsed_ms: Math.max(0, elapsedMs),
    };
  }

  /** Research-line list: main + forks, each with its latest commit summary. */
  listLines(projectId: string): ResearchLine[] {
    this.require(projectId);
    const rows = this.ledger.connection
      .prepare("SELECT task_id, project_id, role, created_at FROM project_tasks WHERE project_id = ? ORDER BY created_at")
      .all(projectId) as TaskRow[];
    return rows.map((row) => ({
      task_id: row.task_id,
      role: row.role as "main" | "fork",
      latest: this.latestVersion(row.task_id),
    }));
  }

  /** Default projection = main branch's latest version (A7 rule 5). */
  defaultProjection(projectId: string): { v: number; verdict: string; commit_hash: string; summary: string } {
    const main = this.listLines(projectId).find((line) => line.role === "main");
    if (main?.latest === undefined || main.latest === null) {
      throw new ProjectHomeError(`project has no committed main-line version: ${projectId}`);
    }
    return main.latest;
  }

  /** 查看最新报告 entry grows automatically after the first commit. */
  hasLatestReport(projectId: string): boolean {
    const main = this.listLines(projectId).find((line) => line.role === "main");
    return main?.latest !== undefined && main.latest !== null;
  }

  listProjects(): ProjectCard[] {
    const rows = this.ledger.connection
      .prepare("SELECT * FROM projects ORDER BY created_at")
      .all() as ProjectRow[];
    return rows.map((row) => this.toCard(row));
  }

  get(projectId: string): ProjectCard | null {
    const row = this.ledger.connection.prepare("SELECT * FROM projects WHERE project_id = ? LIMIT 1").get(projectId) as
      | ProjectRow
      | undefined;
    return row !== undefined ? this.toCard(row) : null;
  }

  archiveProject(projectId: string): void {
    this.require(projectId);
    this.ledger.connection.prepare("UPDATE projects SET status = 'archived' WHERE project_id = ?").run(projectId);
  }

  /** Delete is archived-only (产物默认不冻结、冻结即提交 — 活项目不可删). */
  deleteProject(projectId: string): void {
    const project = this.require(projectId);
    if (project.status !== "archived") {
      throw new ProjectHomeError(`delete blocked: project is not archived (archive first): ${projectId}`);
    }
    const deleteTasks = this.ledger.connection.transaction((): void => {
      this.ledger.connection.prepare("DELETE FROM project_tasks WHERE project_id = ?").run(projectId);
      this.ledger.connection.prepare("DELETE FROM projects WHERE project_id = ?").run(projectId);
    });
    deleteTasks();
  }

  private latestVersion(taskId: string): ResearchLine["latest"] {
    const row = this.ledger.connection
      .prepare("SELECT v, verdict, commit_hash, summary FROM versions WHERE task_id = ? ORDER BY v DESC LIMIT 1")
      .get(taskId) as { v: number; verdict: string; commit_hash: string; summary: string } | undefined;
    return row !== undefined ? { v: row.v, verdict: row.verdict, commit_hash: row.commit_hash, summary: row.summary } : null;
  }

  private toCard(row: ProjectRow): ProjectCard {
    return {
      project_id: row.project_id,
      name: row.name,
      description: row.description,
      status: row.status as "active" | "archived",
      attachments: parseAttachments(row.attachments),
      created_at: row.created_at,
    };
  }

  private require(projectId: string): ProjectCard {
    const project = this.get(projectId);
    if (!project) {
      throw new ProjectHomeError(`unknown project: ${projectId}`);
    }
    return project;
  }
}
