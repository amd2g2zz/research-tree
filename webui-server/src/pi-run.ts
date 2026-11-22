/** Async pi runner over pi's RPC mode (#670, perf #672, settle fix #676,
 * streaming fix #731).

#731 根因：print 模式（`-p`）的 stdout 是**全缓冲**的——实测模型生成 8s
期间 stdout 零输出、退出前 58ms 一把 flush（时间戳级证据见 issue）。基于
stdout data 事件的 onDelta 思考流因此全灭。rpc 模式（`--mode rpc`）在
stdin 上收 `{type:"prompt"}` 命令、stdout 上逐 token 输出事件行
（`message_update.assistantMessageEvent.thinking_delta` = 思考增量），
`message_end` 携带完整 assistant content——thinking/text 块顺序拼接出与
print stdout **语义等价**的最终文本，所以 runPi 的返回值语义不变，
parseTurnOutput / extractJsonObject / 全部调用方零改动。

#729：隔离 cwd 固定复用——pi 把 cwd 写进 system prompt 末尾，逐调用换
目录会打穿 DeepSeek context caching 的最前缀。#676：settle on **exit**
（pi 自身退出即落定，不等被 MCP 孙进程持有的 stdio 管道），超时 SIGKILL
整个进程组。附带收益：message_end 的 usage（cacheRead）打日志，缓存命中
首次可观测。
*/

import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export class PiRunError extends Error {}

/** pi 的固定隔离 cwd（#729 缓存修复）。pi 把工作目录写进 system prompt
 * 末尾（"Current working directory: …"）——system prompt 是请求的最前缀，
 * #706 的每次 mkdtemp 让它逐调用变化，DeepSeek context caching 结构性
 * 0% 命中。隔离的目的只是不让 pi 向上读到仓库的 AGENTS.md（#706），固定
 * 的非仓库空目录完全满足；幂等 mkdir，进程与重启之间复用同一路径。 */
const PI_ISOLATED_CWD = join(tmpdir(), "rt-pi-cwd");

export function piIsolatedCwd(): string {
  mkdirSync(PI_ISOLATED_CWD, { recursive: true });
  return PI_ISOLATED_CWD;
}

interface PiRpcMessage {
  role?: string;
  content?: Array<{ type?: string; thinking?: string; text?: string }>;
  usage?: { input?: number; output?: number; cacheRead?: number; cacheWrite?: number };
}

interface PiRpcEvent {
  type?: string;
  message?: PiRpcMessage;
  assistantMessageEvent?: { type?: string; delta?: string };
}

export interface PiRunHandle {
  promise: Promise<string>;
  /** 请求取消（#742 任务级 stop）：SIGTERM → 宽限 → SIGKILL；promise 以
   * 显式 cancelled 错误拒绝。settle 后调用是 no-op。 */
  cancel: (reason?: string) => void;
}

export function runPi(
  command: string,
  prompt: string,
  timeoutMs = 300_000,
  extraArgs: string[] = [],
  /** streaming hook: fires per thinking_delta chunk as the model generates
   * (#679/#731 — was stdout-based, dead since pi print buffers stdout) */
  onDelta?: (delta: string) => void,
): Promise<string> {
  return runPiCancellable(command, prompt, timeoutMs, extraArgs, onDelta).promise;
}

/** 可取消版 runPi（#742）：任务级 stop 取消在飞的综合/仲裁调用——
 * SIGTERM 整个进程组，宽限（默认 3s）后 SIGKILL；拒绝消息显式
 * "cancelled (reason)"，与超时终止可区分。 */
export function runPiCancellable(
  command: string,
  prompt: string,
  timeoutMs = 300_000,
  extraArgs: string[] = [],
  onDelta?: (delta: string) => void,
  cancelGraceMs = 3_000,
): PiRunHandle {
  let requestCancel: (reason?: string) => void = () => {};
  const promise = new Promise<string>((resolve, reject) => {
    // cwd 隔离（#706 商业化审计）：server 从仓库目录启动时，pi 会向上读
    // AGENTS.md / 项目上下文，把 research-tree 自己当成研究主题注入回答
    // ——结构化调用（turn/extraction/classification）必须在一无所有的
    // 临时目录里跑。#729：目录固定复用（见 piIsolatedCwd）。
    const isolatedCwd = piIsolatedCwd();
    // detached: own process group — lets the timeout SIGKILL the whole tree
    // (pi + its MCP grandchildren), not just pi
    const child = spawn(command, [...extraArgs, "--mode", "rpc"], {
      detached: true,
      cwd: isolatedCwd,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let out = ""; // 最终文本 = assistant message_end 的 thinking+text 块拼接
    let settled = false;
    let timedOut = false;
    let cancelledReason: string | null = null;
    let cancelGrace: ReturnType<typeof setTimeout> | undefined;
    let buf = "";

    const killGroup = (sig: NodeJS.Signals): void => {
      try {
        if (child.pid !== undefined) {
          process.kill(-child.pid, sig); // whole group
        }
      } catch {
        child.kill(sig);
      }
    };

    const timer = setTimeout(() => {
      timedOut = true;
      killGroup("SIGKILL");
    }, timeoutMs);

    // #742 任务级取消：SIGTERM 先行（给 pi 优雅退出的机会），宽限后 SIGKILL
    requestCancel = (reason?: string): void => {
      if (settled || cancelledReason !== null) return;
      cancelledReason = reason ?? "task stop";
      killGroup("SIGTERM");
      cancelGrace = setTimeout(() => killGroup("SIGKILL"), cancelGraceMs);
      cancelGrace.unref?.();
    };

    const settle = (error?: Error): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (cancelGrace !== undefined) clearTimeout(cancelGrace);
      if (error !== undefined) {
        reject(error);
      } else {
        resolve(out);
      }
    };

    // EPIPE 容忍：pi 崩溃时 stdin 写失败会走 exit/reject 路径，不必让
    // stdin error 冒泡成未处理异常
    child.stdin?.on("error", () => {});
    child.stdin?.write(JSON.stringify({ type: "prompt", message: prompt }) + "\n");

    child.stdout?.on("data", (chunk) => {
      buf += String(chunk);
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line === "") continue;
        let ev: PiRpcEvent;
        try {
          ev = JSON.parse(line) as PiRpcEvent;
        } catch {
          continue; // 非 JSON 行（banner 等）直接跳过
        }
        // #731 流式钩子：thinking_delta = 思考增量，逐 token 到达
        const ae = ev.assistantMessageEvent;
        if (ae?.type === "thinking_delta" && typeof ae.delta === "string" && ae.delta !== "" && onDelta !== undefined) {
          onDelta(ae.delta);
        }
        // 最终文本：以最后一条 assistant message_end 为准（thinking+text 顺序拼接）
        if (ev.type === "message_end" && ev.message?.role === "assistant" && Array.isArray(ev.message.content)) {
          out = ev.message.content
            .map((c) => (c.type === "thinking" ? String(c.thinking ?? "") : c.type === "text" ? String(c.text ?? "") : ""))
            .join("");
          const usage = ev.message.usage;
          if (usage !== undefined) {
            console.log(
              `[pi-run] usage input=${usage.input ?? "?"} output=${usage.output ?? "?"} cacheRead=${usage.cacheRead ?? "?"}`,
            );
          }
        }
      }
    });
    child.on("error", (error) => {
      settle(new PiRunError(`pi spawn failed: ${String(error)}`));
    });
    // settle on EXIT (pi itself is done) — never on `close`, which waits for
    // inherited stdio pipes held by outliving extension children
    child.on("exit", (code, signal) => {
      if (cancelledReason !== null) {
        // #742：显式取消优先于超时/信号——调用方（runner 守卫）据此走
        // "任务停止、结果丢弃"的诚实路径
        settle(new PiRunError(`pi call cancelled (${cancelledReason})`));
        return;
      }
      if (timedOut) {
        settle(
          new PiRunError(
            `pi was terminated (timeout ${Math.round(timeoutMs / 1000)}s) — extensions may still be loading or the network is slow; retry`,
          ),
        );
        return;
      }
      if (signal !== null) {
        settle(new PiRunError(`pi was killed by signal ${signal}`));
        return;
      }
      if (code === 0) {
        settle();
      } else {
        settle(new PiRunError(`pi exited with code ${code}: ${out.slice(0, 200)}`));
      }
    });
  });
  return { promise, cancel: (reason?: string) => requestCancel(reason) };
}
