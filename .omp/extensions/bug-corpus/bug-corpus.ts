// Bug Corpus × Oh My Pi — thin adapter over the deterministic core.
//
// All intelligence lives in `uv run bugcorpus` (repository + CLI). This
// extension only registers slash commands and runs the cheap post-edit
// hook. It never synthesizes detectors and never blocks the session:
// a hook that crashes, times out, or errors fails open (CI enforces).
//
// Transport mirrors the in-tree tracelayer gate: async spawn (never
// spawnSync — that parks the JS event loop), explicit stdin, timeout,
// single-registration guard for double-loaded copies.
import { spawn, type ChildProcess } from "node:child_process";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

// trace:v1 id=impl.omp-bugcorpus work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
export default function bugCorpus(pi: ExtensionAPI): void {
  const g = globalThis as unknown as Record<string, unknown>;
  if (g.__bugcorpus_installed === true) return;
  g.__bugcorpus_installed = true;

  pi.setLabel("Bug Corpus");

  const HOOK_TIMEOUT_MS = 30_000;

  // trace:exempt reason=internal-detail
  const runRaw = (
    cmd: string[],
    args: string[],
    input: string,
    cwd?: string,
  ): Promise<{ out: string; spawned: boolean }> => {
    const { promise, resolve } = Promise.withResolvers<{ out: string; spawned: boolean }>();
    let out = "";
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      resolve({ out, spawned: true });
    }, HOOK_TIMEOUT_MS);
    // trace:exempt reason=internal-detail
    const finish = (text: string, spawned: boolean): void => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve({ out: text, spawned });
    };
    let child: ChildProcess | undefined;
    try {
      child = spawn(cmd[0], [...cmd.slice(1), ...args], { cwd });
    } catch {
      finish("", false);
      return promise;
    }
    child.stdout?.on("data", (d: unknown) => {
      out += String(d);
    });
    child.on("error", () => finish("", false));
    child.on("close", () => finish(out, true));
    try {
      child.stdin?.write(input);
      child.stdin?.end();
    } catch {
      finish("", false);
    }
    return promise;
  };

  // Prefer the installed `bugcorpus` entry point; fall back to the dev
  // checkout form. The fallback runs only when the binary is missing.
  // trace:exempt reason=internal-detail
  const run = async (args: string[], input: string, cwd?: string): Promise<string> => {
    const first = await runRaw(["bugcorpus"], args, input, cwd);
    if (first.spawned) return first.out;
    return (await runRaw(["uv", "run", "bugcorpus"], args, input, cwd)).out;
  };

  // One call shape for all user-facing notes; three call sites share it.
  // trace:exempt reason=internal-detail
  const notify = (
    ctx: { ui?: { notify?: (text: string, level?: string) => void } },
    text: string,
  ): void => {
    try {
      ctx.ui?.notify?.(text, "info");
    } catch {
      // notification is best-effort
    }
  };

  pi.registerCommand("bug-corpus", {
    description: "Show Bug Corpus status (bugs, families, detectors)",
    handler: async (_args, ctx) => {
      const raw = await run(["--json", "detector", "list"], "", ctx.cwd);
      let n = "?";
      try {
        n = String((JSON.parse(raw) as unknown[]).length);
      } catch {
        // fall through with unknown count
      }
      notify(ctx, `Bug Corpus: ${n} detectors registered. Run /bug-scan to scan.`);
    },
  });

  pi.registerCommand("bug-learn", {
    description: "Learn the just-fixed bug into Bug Corpus (guides detector synthesis)",
    handler: async (_args, ctx) => {
      notify(
        ctx,
        "Bug Corpus learn: fix must be proven by normal tests first, then run `uv run bugcorpus learn --title \"...\"` and follow the bug-corpus skill (invariant, siblings, cheapest detector, fixtures, shadow first).",
      );
    },
  });

  pi.registerCommand("bug-scan", {
    description: "Run Bug Corpus detectors (PR profile)",
    handler: async (_args, ctx) => {
      const raw = await run(["scan", "--profile", "pr"], "", ctx.cwd);
      notify(ctx, raw ? `Bug Corpus scan:\n${raw.slice(0, 1500)}` : "Bug Corpus scan clean.");
    },
  });

  // Session announcement: verified load state, silent outside enrolled repos.
  // The CLI prints nothing without a .bugcorpus directory, so a bare notify
  // of empty output would be noise: only notify when it says something.
  pi.on("session_start", async (_event, ctx) => {
    const out = await run(["hooks", "session-start"], "", ctx.cwd);
    if (out.trim()) notify(ctx, out.trim().slice(0, 800));
  });

  pi.on("tool_result", async (event, ctx) => {
    if (event.toolName !== "edit" && event.toolName !== "write") return;
    const input = (event.input ?? {}) as Record<string, unknown>;
    const path = input["path"] ?? input["file_path"];
    if (typeof path !== "string" || !path.endsWith(".py")) return;
    const body = JSON.stringify({ tool_name: event.toolName, tool_input: event.input });
    const out = await run(["hooks", "post-tool-use"], body, ctx.cwd);
    if (!out.trim() || !Array.isArray(event.content)) return;
    return {
      content: [...event.content, { type: "text", text: `\n\n<BugCorpus>\n${out}\n</BugCorpus>` }],
    };
  });
}
