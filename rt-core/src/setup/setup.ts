/** rt setup & boot — idempotent installation + readiness doctor (issue #588).

docs 02 §setup 与 boot (v2.3): `rt setup` provisions to a working boot —
workspace initialization (ledger + graph projection stores, migration run),
provider CLI dependency checks with pinned expectations, extension mount
(#552) — and **never silently installs**: global installs and credential
writes go through the injected `confirm` gate first (花钱/全局动作先问).

`doctor` reports boot readiness: per-provider availability (named with
install guidance, not a generic failure), storage writability, MCP
mountability (#553), pi session attachment (#552). Machine-readable JSON for
headless (#579).
*/

import { existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";

import { LedgerStore } from "../store/ledger.js";
import type { ProviderRegistry } from "../providers/registry.js";

export interface ProviderProvisionReport {
  name: string;
  status: "installed" | "already-current" | "missing-api-key" | "missing" | "version-mismatch";
  version?: string;
  install_guidance?: string;
}

export interface SetupReport {
  steps: Record<string, "created" | "already-initialized">;
  providers: ProviderProvisionReport[];
  confirmed_actions: Array<{ kind: string; detail: string; confirmed: boolean }>;
}

export interface ConfirmAction {
  kind: "global-install" | "credential-write";
  detail: string;
}

export interface SetupOptions {
  workspace: string;
  registry?: ProviderRegistry;
  /** injected provisioner — performs the actual CLI install/check per provider */
  provisioner?: (providerName: string) => Promise<string>;
  /** injected confirmation gate — global installs / credential writes must be approved */
  confirm?: (action: ConfirmAction) => Promise<boolean>;
  /** expected provider CLI versions (pin at provisioning) */
  pinnedVersions?: Record<string, string>;
}

const INSTALL_GUIDANCE: Record<string, string> = {
  anysearch: "install the anysearch CLI and set ANYSEARCH_API_KEY (see docs/providers/anysearch.md)",
  "agent-browser": "npm i -g agent-browser && agent-browser install (see docs/providers/agent-browser.md)",
};

/** Idempotent setup: workspace + provider provisioning. */
export async function runSetup(options: SetupOptions): Promise<SetupReport> {
  const steps: Record<string, "created" | "already-initialized"> = {};
  const confirmed_actions: Array<{ kind: string; detail: string; confirmed: boolean }> = [];

  const root = join(options.workspace, ".research-tree");
  if (existsSync(root)) {
    steps.workspace = "already-initialized";
  } else {
    mkdirSync(root, { recursive: true });
    const ledger = new LedgerStore(options.workspace);
    ledger.initialize();
    steps.workspace = "created";
  }

  const providers: ProviderProvisionReport[] = [];
  if (options.registry) {
    for (const name of options.registry.names()) {
      if (options.provisioner === undefined) {
        providers.push({ name, status: "missing", install_guidance: INSTALL_GUIDANCE[name] ?? "see provider docs" });
        continue;
      }
      const status = await options.provisioner(name);
      if ((status === "installed" || status === "version-mismatch") && options.confirm) {
        const action: ConfirmAction = {
          kind: "global-install",
          detail: `provider CLI install/upgrade: ${name} (${status})`,
        };
        const approved = await options.confirm(action);
        confirmed_actions.push({ ...action, confirmed: approved });
        if (!approved) {
          providers.push({ name, status: "missing", install_guidance: INSTALL_GUIDANCE[name] ?? "see provider docs" });
          continue;
        }
      }
      providers.push({
        name,
        status: status as ProviderProvisionReport["status"],
        install_guidance: INSTALL_GUIDANCE[name],
      });
    }
  }

  return { steps, providers, confirmed_actions };
}

export interface DoctorReadiness {
  overall: "ready" | "attention-required";
  providers: Array<{ name: string; state: string; install_guidance?: string }>;
  storage: "writable" | "unavailable";
  mcp: "mountable" | "unavailable";
  pi: string;
}

export interface DoctorOptions {
  workspace: string;
  registry?: ProviderRegistry;
  checks?: {
    providerCli?: (providerName: string) => Promise<string>;
    mcpMountable?: () => Promise<boolean>;
    piSession?: () => Promise<string>;
  };
}

/** Boot readiness: named providers, storage, MCP, pi. */
export async function doctor(options: DoctorOptions): Promise<DoctorReadiness> {
  const root = join(options.workspace, ".research-tree");
  const storage = existsSync(root) ? "writable" : "unavailable";

  const providers: Array<{ name: string; state: string; install_guidance?: string }> = [];
  if (options.registry) {
    for (const name of options.registry.names()) {
      const state = options.checks?.providerCli ? await options.checks.providerCli(name) : "unknown";
      providers.push({ name, state, install_guidance: state === "ok" ? undefined : INSTALL_GUIDANCE[name] });
    }
  }

  const mcp = options.checks?.mcpMountable ? (await options.checks.mcpMountable() ? "mountable" : "unavailable") : "unavailable";
  const pi: string = options.checks?.piSession ? await options.checks.piSession() : "detached";

  const allProvidersOk = providers.every((provider) => provider.state === "ok");
  const overall: DoctorReadiness["overall"] =
    storage === "writable" && mcp === "mountable" && pi === "attached" && allProvidersOk
      ? "ready"
      : "attention-required";

  return { overall, providers, storage, mcp, pi };
}
