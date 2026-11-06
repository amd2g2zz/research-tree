/** Shared WS-RPC + REST client (issue #690). One socket, promise RPC, and the
 * "turn-delta" stream event used for chain-of-thought streaming. */

let ws: WebSocket | undefined;
let pending: Promise<WebSocket> | undefined;
let rpcId = 0;
let deltaCb: ((delta: string) => void) | undefined;

export function connectWs(): Promise<WebSocket> {
	if (ws?.readyState === WebSocket.OPEN) return Promise.resolve(ws);
	pending ??= new Promise((resolve, reject) => {
		const proto = location.protocol === "https:" ? "wss" : "ws";
		const socket = new WebSocket(`${proto}://${location.host}/ws`);
		socket.onopen = () => {
			ws = socket;
			resolve(socket);
		};
		socket.onerror = () => reject(new Error("ws connect failed"));
		socket.onmessage = (ev) => {
			const msg = JSON.parse(ev.data) as { event?: string; delta?: string };
			if (msg.event === "turn-delta" && deltaCb !== undefined)
				deltaCb(msg.delta ?? "");
		};
	});
	return pending;
}

export async function rpc(
	method: string,
	params?: Record<string, unknown>,
	timeoutMs = 330_000,
): Promise<Record<string, unknown>> {
	const socket = await connectWs();
	const id = ++rpcId;
	return new Promise((resolve, reject) => {
		const settle = (fn: () => void) => {
			clearTimeout(timer);
			socket.removeEventListener("message", on);
			fn();
		};
		const on = (ev: MessageEvent) => {
			const msg = JSON.parse(ev.data) as {
				id?: number;
				ok?: boolean;
				error?: string;
				result?: Record<string, unknown>;
			};
			if (msg.id !== id) return;
			settle(() => {
				if (msg.ok) resolve(msg.result ?? {});
				else reject(new Error(msg.error ?? "unknown rpc error"));
			});
		};
		// 服务端可能在 ws 半开时被重启——请求进入僵尸 socket 会永远无响应。
		// 超时后丢弃该 socket，下一次 rpc 重建连接（默认 > pi 的 300s 上限）。
		const timer = setTimeout(() => {
			settle(() => reject(new Error(`rpc ${method} 超时`)));
			if (ws === socket) {
				ws = undefined;
				pending = undefined;
				try {
					socket.close();
				} catch {
					/* already closed */
				}
			}
		}, timeoutMs);
		socket.addEventListener("message", on);
		socket.send(JSON.stringify({ id, method, params: params ?? {} }));
	});
}

export function onDelta(cb: (delta: string) => void): void {
	deltaCb = cb;
}

export async function rest<T = Record<string, unknown>>(
	path: string,
): Promise<T> {
	const res = await fetch(path);
	if (!res.ok) {
		const body = (await res.json()) as { error?: string };
		throw new Error(`${res.status}: ${String(body.error ?? res.statusText)}`);
	}
	return (await res.json()) as T;
}

/** Subscribe to raw engine events broadcast on the shared socket.
 * The callback receives the engine `line` payload (console stream). */
export async function onEngine(cb: (line: string) => void): Promise<() => void> {
	const socket = await connectWs();
	const on = (ev: MessageEvent) => {
		const msg = JSON.parse(ev.data) as { event?: string; line?: string };
		if (msg.event === "engine") cb(String(msg.line ?? ""));
	};
	socket.addEventListener("message", on);
	return () => socket.removeEventListener("message", on);
}
