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
}
