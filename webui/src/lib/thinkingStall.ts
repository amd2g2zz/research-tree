// #754：思考停滞可见性——面板静止时用户无法分辨「还在想」还是「死了」。
// 计时 + 停滞提示：>90s 无新 delta 标注响应缓慢（高峰限流可能，见 #733）。
// 纯函数：App.tsx 的 Collapse label 与测试共用同一判定。

export const THINKING_STALL_THRESHOLD_MS = 90_000;

export function thinkingLabel(
	elapsedMs: number,
	msSinceLastDelta: number,
): string {
	const secs = Math.max(1, Math.round(elapsedMs / 1000));
	const stalled = msSinceLastDelta > THINKING_STALL_THRESHOLD_MS;
	return stalled
		? `rt · 思考中 ${secs}s · 响应缓慢（高峰限流可能）`
		: `rt · 思考中 ${secs}s`;
}
