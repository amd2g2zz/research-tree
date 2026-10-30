/** Named provider registry (issue #584).

Config-driven selection with a default; manifests only — full usage loads on
demand via the lazy-disclosure layer (#589). Credentials never enter the
registry: providers carry their own injected config.
*/

import type { DataSourceProvider, ProviderManifest } from "./types.js";

export class ProviderRegistryError extends Error {}

export class ProviderRegistry {
  private providers = new Map<string, DataSourceProvider>();
  private defaultName: string | null = null;

  register(provider: DataSourceProvider): void {
    const name = provider.manifest.name;
    if (this.providers.has(name)) {
      throw new ProviderRegistryError(`provider already registered: ${name}`);
    }
    this.providers.set(name, provider);
  }

  setDefault(name: string): void {
    if (!this.providers.has(name)) {
      throw new ProviderRegistryError(`cannot set default: unknown provider ${name}`);
    }
    this.defaultName = name;
  }

  get(name: string): DataSourceProvider | undefined {
    return this.providers.get(name);
  }

  /** The default provider (anysearch in the bundled configuration). */
  default(): DataSourceProvider {
    const name = this.defaultName ?? (this.providers.has("anysearch") ? "anysearch" : null);
    if (name === null) {
      throw new ProviderRegistryError("no default provider configured");
    }
    return this.providers.get(name)!;
  }

  names(): string[] {
    return [...this.providers.keys()].sort();
  }

  /** Manifest lines only — the lazy-disclosure surface (#589). */
  manifests(): ProviderManifest[] {
    return this.names().map((name) => this.providers.get(name)!.manifest);
  }

  // ------------------------------------------ lazy disclosure (#589, #584 base)
  // The registry holds lightweight manifests; full usage guides enter context
  // only for selected providers (discovery-stub precedent, #501 two-layer
  // contract). Context discipline: loadedUsage ⊆ selected.

  private selectedNames = new Set<string>();
  private usageCache = new Map<string, string>();

  /** Mark a provider selected for this run/context (its usage may now load). */
  select(name: string): void {
    if (!this.providers.has(name)) {
      throw new ProviderRegistryError(`cannot select: unknown provider ${name}`);
    }
    this.selectedNames.add(name);
  }

  selected(): string[] {
    return [...this.selectedNames].sort();
  }

  searchProviders(criteria: { capability?: "search" | "fetch"; kind?: string; keyword?: string }): ProviderManifest[] {
    return this.manifests().filter((manifest) => {
      if (criteria.capability && !manifest.capabilities[criteria.capability]) {
        return false;
      }
      if (criteria.kind && !manifest.kinds.includes(criteria.kind)) {
        return false;
      }
      if (criteria.keyword) {
        const haystack = `${manifest.name} ${manifest.description} ${manifest.kinds.join(" ")}`.toLowerCase();
        if (!haystack.includes(criteria.keyword.toLowerCase())) {
          return false;
        }
      }
      return true;
    });
  }

  /** Load the full usage guide for a SELECTED provider (cached by name). */
  loadUsage(name: string, load: (usagePointer: string) => string): string {
    if (!this.selectedNames.has(name)) {
      throw new ProviderRegistryError(`usage load refused: ${name} is not selected`);
    }
    const cached = this.usageCache.get(name);
    if (cached !== undefined) {
      return cached;
    }
    const provider = this.providers.get(name)!;
    const usage = load(provider.manifest.usage);
    this.usageCache.set(name, usage);
    return usage;
  }

  loadedUsageCount(): number {
    return this.usageCache.size;
  }
}
