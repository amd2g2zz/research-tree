/** Shared WS-RPC + REST client (issue #690). One socket, promise RPC, and the
 * "turn-delta" stream event used for chain-of-thought streaming.
 * P1-3（#706）：断线自动重连（指数退避，封顶 8s）+ 连接状态订阅——服务重启
 * 不再留下僵尸 socket（挂 330s）或静默断更。 */

let ws: WebSocket | undefined;
let pending: Promise<WebSocket> | undefined;
let rpcId = 0;
let deltaCb: ((delta: string) => void) | undefined;
const eventCbs = new Set<(ev: { event?: string; task_id?: string }) => void>();

/** 订阅 turn 生命周期事件（turn-start/turn-end）——刷新/换端后重新挂流 */
export function onTurnEvent(
	cb: (ev: { event?: string; task_id?: string }) => void,
): () => void {
	eventCbs.add(cb);
	return () => eventCbs.delete(cb);
}
let wsStatus: "connecting" | "open" | "closed" = "closed";
const statusCbs = new Set<(s: "connecting" | "open" | "closed") => void>();
let reconnectAttempt = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

function setStatus(s: "connecting" | "open" | "closed"): void {
	wsStatus = s;
	for (const cb of statusCbs) cb(s);
}

export function onWsStatus(
	cb: (s: "connecting" | "open" | "closed") => void,
): () => void {
	statusCbs.add(cb);
	cb(wsStatus);
	return () => statusCbs.delete(cb);
}

function scheduleReconnect(): void {
	if (reconnectTimer !== undefined) return;
	const delay = Math.min(1000 * 2 ** reconnectAttempt, 8000);
	reconnectAttempt += 1;
	reconnectTimer = setTimeout(() => {
		reconnectTimer = undefined;
		pending = undefined;
		void connectWs().catch(() => scheduleReconnect());
	}, delay);
}

export function connectWs(): Promise<WebSocket> {
	if (ws?.readyState === WebSocket.OPEN) return Promise.resolve(ws);
	if (pending !== undefined) return pending;
	setStatus("connecting");
	pending = new Promise((resolve, reject) => {
		const proto = location.protocol === "https:" ? "wss" : "ws";
		const socket = new WebSocket(`${proto}://${location.host}/ws`);
		socket.onopen = () => {
			reconnectAttempt = 0;
			ws = socket;
			setStatus("open");
			resolve(socket);
		};
		socket.onclose = () => {
			if (ws === socket) ws = undefined;
			if (pending !== undefined) {
				pending = undefined;
				setStatus("closed");
				scheduleReconnect();
			}
		};
		socket.onerror = () => {
			if (pending === undefined) return;
			// onclose follows — reconnect scheduled there
		};
		socket.onmessage = (ev) => {
			const msg = JSON.parse(ev.data) as {
				event?: string;
				delta?: string;
				task_id?: string;
			};
			if (msg.event === "turn-delta" && deltaCb !== undefined)
				deltaCb(msg.delta ?? "");
			if (msg.event === "turn-start" || msg.event === "turn-end") {
				for (const cb of eventCbs) cb(msg);
			}
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
export async function onEngine(
	cb: (line: string) => void,
): Promise<() => void> {
	const socket = await connectWs();
	const on = (ev: MessageEvent) => {
		const msg = JSON.parse(ev.data) as { event?: string; line?: string };
		if (msg.event === "engine") cb(String(msg.line ?? ""));
	};
	socket.addEventListener("message", on);
	return () => socket.removeEventListener("message", on);
}
