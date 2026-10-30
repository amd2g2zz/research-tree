/** Canonical JSON: recursively sorted keys, stable serialization — the hash-chain input. */

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export function canonicalJson(value: Json): string {
  if (value === undefined) {
    return "null"; // never crash on a dropped key — canonical null
  }
  if (value === null || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item as Json)).join(",")}]`;
  }
  const keys = Object.keys(value).sort();
  const body = keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key] as Json)}`).join(",");
  return `{${body}}`;
}

export function canonicalJsonBytes(value: Json): Buffer {
  return Buffer.from(canonicalJson(value), "utf8");
}
