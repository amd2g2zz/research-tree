/** Default pi extensions tests (issue #664): idempotent provisioning of the
 * five default extensions into pi's settings.json — installer injected, npm
 * never actually runs in tests. */

import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { DEFAULT_PI_EXTENSIONS, ensurePiExtensions, extensionStatuses } from "../src/pi-extensions.js";

function fixtureDir(initialPackages: string[] = []): string {
  const dir = mkdtempSync(join(tmpdir(), "rt-ext-"));
  writeFileSync(join(dir, "settings.json"), JSON.stringify({ packages: initialPackages }));
  return dir;
}

describe("default pi extensions (issue #664)", () => {
  it("installs missing extensions into settings with the injected installer", () => {
    const dir = fixtureDir(["../../../../private/tmp/pi-host/pi-subagents-nb"]);
    const installedPkgs: string[] = [];
    const result = ensurePiExtensions({
      settingsDir: dir,
      installer: (pkg) => {
        installedPkgs.push(pkg);
        return { path: `/fake/npm/node_modules/${pkg}` };
      },
    });
    expect(result.installed).toEqual([...DEFAULT_PI_EXTENSIONS]); // all 5 missing
    expect(result.failed).toEqual([]);
    const settings = JSON.parse(readFileSync(join(dir, "settings.json"), "utf8")) as { packages: string[] };
    expect(settings.packages).toContain("/fake/npm/node_modules/billion-context");
    expect(settings.packages).toHaveLength(6); // pi-subagents + 5
  });

  it("is idempotent: already-present packages are skipped (settings-path or npm: form)", () => {
    const dir = fixtureDir([
      "npm:billion-context",
      "/x/node_modules/context-mode",
      "@juicesharp/rpiv-ask-user-question",
    ]);
    const result = ensurePiExtensions({
      settingsDir: dir,
      installer: (pkg) => {
        return { path: `/fake/${pkg}` };
      },
    });
    expect(result.present.sort()).toEqual(
      ["@juicesharp/rpiv-ask-user-question", "billion-context", "context-mode"].sort(),
    );
    expect(result.installed.sort()).toEqual(["pi-mcp-adapter", "pi-web-access"].sort());
  });

  it("failures are reported per-extension without corrupting settings", () => {
    const dir = fixtureDir([]);
    const result = ensurePiExtensions({
      settingsDir: dir,
      installer: (pkg) => {
        if (pkg === "pi-mcp-adapter") {
          throw new Error("npm EACCES");
        }
        return { path: `/fake/${pkg}` };
      },
    });
    expect(result.installed).toHaveLength(4);
    expect(result.failed).toEqual([{ name: "pi-mcp-adapter", error: "npm EACCES" }]);
    const settings = JSON.parse(readFileSync(join(dir, "settings.json"), "utf8")) as { packages: string[] };
    expect(settings.packages.every((p) => p.startsWith("/fake/") || p.includes("pi-subagents") === false)).toBe(true);
    expect(settings.packages.some((p) => p.includes("pi-mcp-adapter"))).toBe(false); // failed one not added
  });

  it("extensionStatuses reads installed/missing from settings", () => {
    const dir = fixtureDir(["/x/node_modules/billion-context"]);
    const statuses = extensionStatuses(dir);
    expect(statuses.find((s) => s.name === "billion-context")?.installed).toBe(true);
    expect(statuses.find((s) => s.name === "pi-web-access")?.installed).toBe(false);
  });
});
