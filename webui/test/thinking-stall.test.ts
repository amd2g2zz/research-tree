import { describe, expect, it } from "vitest";
import {
	THINKING_STALL_THRESHOLD_MS,
	thinkingLabel,
} from "../src/lib/thinkingStall";

// #754：思考停滞可见性——面板静止时用户无法分辨「还在想」还是「死了」。
// 计时 + 停滞提示（>90s 无新 delta → 标注响应缓慢）抽纯函数，断言显示语义。
describe("thinkingLabel", () => {
	it("刚开始思考（<1s）从 1s 起步，不显示 0s", () => {
		expect(thinkingLabel(200, 200)).toBe("rt · 思考中 1s");
	});

	it("思考中显示实时秒数", () => {
		expect(thinkingLabel(45_000, 500)).toBe("rt · 思考中 45s");
	});

	it("秒数四舍五入", () => {
		expect(thinkingLabel(59_600, 400)).toBe("rt · 思考中 60s");
	});

	it("距上次 delta 恰在阈值内：不提示停滞", () => {
		expect(thinkingLabel(120_000, THINKING_STALL_THRESHOLD_MS)).toBe(
			"rt · 思考中 120s",
		);
	});

	it("距上次 delta 超阈值：标注响应缓慢（高峰限流可能）", () => {
		expect(thinkingLabel(120_000, THINKING_STALL_THRESHOLD_MS + 1)).toBe(
			"rt · 思考中 120s · 响应缓慢（高峰限流可能）",
		);
	});
});
