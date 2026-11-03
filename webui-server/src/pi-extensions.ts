/** Default pi extensions (issue #664, #588 provisioning discipline).

用户裁定 2026-11-03: these five extensions ship in the DEFAULT pi
provisioning list (alongside pi-subagents):

- billion-context
- @juicesharp/rpiv-ask-user-question
- pi-mcp-adapter
- context-mode
- pi-web-access

pi.dev/packages/<name> is an index — the official install command for each
is `pi install npm:<name>`. Machines where the global npm prefix is not
writable (EACCES on /usr/local) fall back to a **local npm prefix at
~/.pi/agent/npm** with the package paths appended to pi's settings.json
`packages` (same pattern as the proven pi-subagents install).

#588 discipline: installs are NEVER silent — provisioning runs only on the
explicit settings-page action, and every result lands in the audit log.
*/

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

export const DEFAULT_PI_EXTENSIONS = [
  "billion-context",
  "@juicesharp/rpiv-ask-user-question",
  "pi-mcp-adapter",
  "context-mode",
  "pi-web-access",
] as const;

export type ExtensionInstaller = (pkg: string) => { path: string };

export interface ExtensionStatus {
  name: string;
  installed: boolean;
  source: "settings-path" | "npm-global" | null;
}

export interface EnsureResult {
  installed: string[];
  present: string[];
  failed: Array<{ name: string; error: string }>;
}

function readJson(path: string): Record<string, unknown> | null {
  if (!existsSync(path)) {
    return null;
  }
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function settingsPackages(settingsPath: string): string[] {
  const settings = readJson(settingsPath);
  const pkgs = settings?.packages;
  return Array.isArray(pkgs) ? (pkgs.filter((p) => typeof p === "string") as string[]) : [];
}

/** Local npm prefix used when the global prefix is not writable. */
export function localNpmPrefix(settingsDir: string): string {
  return join(settingsDir, "npm");
}

/** Default installer: `pi install npm:<pkg>` when the pi command exists;
 * otherwise npm-install into the local prefix under ~/.pi/agent/npm and
 * return that package dir as the settings path. */
export function defaultInstaller(settingsDir: string, piCommand: string | null): ExtensionInstaller {
  return (pkg: string): { path: string } => {
    if (piCommand !== null) {
      const result = spawnSync(piCommand, ["install", `npm:${pkg}`], { encoding: "utf8", timeout: 300_000 });
      if (result.status === 0) {
        return { path: `npm:${pkg}` };
      }
      // fall through to the local-prefix fallback (global npm EACCES etc.)
    }
    const prefix = localNpmPrefix(settingsDir);
    const run = spawnSync("npm", ["install", "--no-audit", "--no-fund", pkg], {
      encoding: "utf8",
      cwd: prefix,
      timeout: 300_000,
    });
    const pkgPath = join(prefix, "node_modules", pkg);
    if (run.status !== 0 || !existsSync(pkgPath)) {
      throw new Error(`npm install ${pkg} failed (code ${run.status ?? "?"}) — both pi install and local prefix unavailable`);
    }
    return { path: pkgPath };
  };
}

/** Idempotent provisioning: packages already referenced in settings.json are
 * skipped; missing ones are installed and their paths appended. */
export function ensurePiExtensions(options: {
  settingsDir?: string;
  installer?: ExtensionInstaller;
  piCommand?: string | null;
  /** test isolation: run npm in a temp cwd (never the repo) */
  cwd?: string;
} = {}): EnsureResult {
  const settingsDir = options.settingsDir ?? join(homedir(), ".pi", "agent");
  const settingsPath = join(settingsDir, "settings.json");
  const installer = options.installer ?? defaultInstaller(settingsDir, options.piCommand ?? resolvePiCommand());
  mkdirSync(settingsDir, { recursive: true });

  const packages = settingsPackages(settingsPath);
  const result: EnsureResult = { installed: [], present: [], failed: [] };
  const updated = [...packages];
  for (const name of DEFAULT_PI_EXTENSIONS) {
    const already = packages.some((p) => p === name || p === `npm:${name}` || p.endsWith(`/${name}`) || p.endsWith(`node_modules/${name}`));
    if (already) {
      result.present.push(name);
      continue;
    }
    try {
      const { path } = installer(name);
      updated.push(path);
      result.installed.push(name);
    } catch (error) {
      result.failed.push({ name, error: String(error instanceof Error ? error.message : error) });
    }
  }
  if (result.installed.length > 0) {
    const settings = readJson(settingsPath) ?? {};
    settings.packages = updated;
    const tmp = join(tmpdir(), `pi-settings-${process.pid}-${Date.now()}.json`);
    writeFileSync(tmp, JSON.stringify(settings, null, 2));
    // atomic-ish: write tmp then copy over (rename across devices may fail)
    writeFileSync(settingsPath, readFileSync(tmp, "utf8"));
  }
  return result;
}

export function resolvePiCommand(): string | null {
  const fromEnv = process.env.RT_PI_CMD;
  if (fromEnv !== undefined && fromEnv !== "" && existsSync(fromEnv)) {
    return fromEnv;
  }
  const probe = spawnSync("which", ["pi"], { encoding: "utf8" });
  if (probe.status === 0 && probe.stdout.trim() !== "" && existsSync(probe.stdout.trim())) {
    return probe.stdout.trim();
  }
  const scratch = "/private/tmp/pi-host/node_modules/.bin/pi";
  return existsSync(scratch) ? scratch : null;
}

/** Status per default extension against settings.json packages. */
export function extensionStatuses(settingsDir: string = join(homedir(), ".pi", "agent")): ExtensionStatus[] {
  const packages = settingsPackages(join(settingsDir, "settings.json"));
  return DEFAULT_PI_EXTENSIONS.map((name) => {
    const installed = packages.some((p) => p === name || p === `npm:${name}` || p.endsWith(`/${name}`) || p.endsWith(`node_modules/${name}`));
    return { name, installed, source: installed ? ("settings-path" as const) : null };
  });
}
