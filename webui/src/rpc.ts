/** Shared WebSocket RPC + REST client (issue #685).

Single connection per tab, JSON-RPC over WebSocket for mutations,
fetch for reads. All server communication goes through here.
*/

let ws: WebSocket | undefined = undefined;
let wsPromise: Promise<WebSocket> | null = null;
let msgId = 0;

export function getSocket(): Promise<WebSocket> {
  if (ws !== undefined && ws.readyState === WebSocket.OPEN) {
    return Promise.resolve(ws);
  }
  if (wsPromise !== null) {
    return wsPromise;
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  wsPromise = new Promise((resolve, reject) => {
    const socket = new WebSocket(`${proto}://${location.host}/ws`);
    socket.onopen = () => {
      ws = socket;
      resolve(socket);
    };
    socket.onerror = reject;
  });
  return wsPromise;
}

export type DeltaHandler = (delta: string) => void;

let deltaHandler: DeltaHandler | null = null;

export function onTurnDelta(handler: DeltaHandler): void {
  deltaHandler = handler;
}

export async function rpc(
  wsOrMethod: WebSocket | string,
  methodOrParams?: string | Record<string, unknown>,
  maybeParams?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const socket = typeof wsOrMethod === "string" ? await getSocket() : wsOrMethod;
  const method = typeof wsOrMethod === "string" ? wsOrMethod : methodOrParams!;
  const params = typeof wsOrMethod === "string" ? methodOrParams : maybeParams;
  const id = Date.now() + Math.random();
  return new Promise((resolve, reject) => {
    const onMessage = (ev: MessageEvent): void => {
      const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
      if (msg.event === "turn-delta" && deltaHandler !== null) {
        deltaHandler(String(msg.delta ?? ""));
        return;
      }
      if (msg.id === id) {
        socket.removeEventListener("message", onMessage);
        if (msg.ok === true) {
          resolve(msg.result as Record<string, unknown>);
        } else {
          reject(new Error(String(msg.error)));
        }
      }
    };
    socket.addEventListener("message", onMessage);
    socket.send(JSON.stringify({ id, method, params: params ?? {} }));
  });
}

export async function api(path: string): Promise<Record<string, unknown>> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${res.status}: ${String((await res.json()).error ?? res.statusText)}`);
  }
  return (await res.json()) as Record<string, unknown>;
}
