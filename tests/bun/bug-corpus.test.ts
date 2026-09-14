// OMP extension contract: registers commands once, hooks cheap, fails open.
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { execFileSync } from "node:child_process";
import { describe, expect, test } from "bun:test";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import factory from "../../adapters/omp/bug-corpus.ts";
interface Ctx {
  ui?: { notify?: (text: string, level?: string) => void };
  cwd?: string;
}

interface CommandDef {
  description: string;
  handler: (args: unknown, ctx: Ctx) => Promise<void>;
}

interface ToolResultEvent {
  toolName?: string;
  input?: Record<string, unknown>;
  content?: unknown;
}

interface StubPi {
  setLabel: (label: string) => void;
  registerCommand: (name: string, def: CommandDef) => void;
  on: (event: string, fn: (event: ToolResultEvent, ctx: Ctx) => Promise<unknown>) => void;
  ui: { notify: (text: string) => void };
}

function stub() {
  // fresh simulated process per test: the double-load guard is module-global
  delete (globalThis as Record<string, unknown>).__bugcorpus_installed;
  const commands = new Map<string, CommandDef>();
  const handlers = new Map<string, (event: ToolResultEvent, ctx: Ctx) => Promise<unknown>>();
  const notes: string[] = [];
  const pi: StubPi = {
    setLabel() {},
    registerCommand: (n, d) => commands.set(n, d),
    on: (e, f) => handlers.set(e, f),
    ui: { notify: (t) => notes.push(t) },
  };
  return { commands, handlers, notes, pi };
}

function load(s: ReturnType<typeof stub>): void {
  factory(s.pi as unknown as ExtensionAPI);
}

describe("bug-corpus extension", () => {
  test("registers three commands and three hooks, once across double load", () => {
    const s = stub();
    load(s);
    load(s);
    expect([...s.commands.keys()]).toEqual(["bug-corpus", "bug-learn", "bug-scan"]);
    expect([...s.handlers.keys()]).toEqual(["session_start", "session_switch", "tool_result"]);
  });

  test("tool_result ignores non-edit tools and non-python files", async () => {
    const s = stub();
    load(s);
    const hook = s.handlers.get("tool_result");
    if (!hook) throw new Error("tool_result handler not registered");
    expect(await hook({ toolName: "read", input: {}, content: [] }, {})).toBeUndefined();
    expect(
      await hook({ toolName: "edit", input: { path: "README.md" }, content: [] }, {}),
    ).toBeUndefined();
  });

  test("bug-learn notifies guidance without spawning", async () => {
    const s = stub();
    load(s);
    const cmd = s.commands.get("bug-learn");
    if (!cmd) throw new Error("bug-learn not registered");
    await cmd.handler({}, s.pi);
    expect(s.notes.join("\n")).toContain("uv run bugcorpus learn");
  });

  test("edit of a clean python file runs transport and stays silent", async () => {
    const s = stub();
    load(s);
    const hook = s.handlers.get("tool_result");
    if (!hook) throw new Error("tool_result handler not registered");
    const repo = new URL("../..", import.meta.url).pathname.replace(/\/$/, "");
    const out = await hook(
      { toolName: "edit", input: { path: `${repo}/bugcorpus/cli.py` }, content: [] },
      { cwd: repo },
    );
    expect(out).toBeUndefined(); // no findings in cli.py -> silent
  }, 120000); // nested `uv run` under pytest contends the uv lock; extension caps at 30s

  test("session_start announces verified state in enrolled repos", async () => {
    const s = stub();
    load(s);
    const hook = s.handlers.get("session_start");
    if (!hook) throw new Error("session_start handler not registered");
    const repo = new URL("../..", import.meta.url).pathname.replace(/\/$/, "");
    await hook({}, { cwd: repo, ui: s.pi.ui });
    expect(s.notes.join("\n")).toContain("Bug Corpus");
    expect(s.notes.join("\n")).toContain("loaded");
  }, 120000);

  test("session_start stays silent outside enrolled repos", async () => {
    const s = stub();
    load(s);
    const hook = s.handlers.get("session_start");
    if (!hook) throw new Error("session_start handler not registered");
    const prev = process.env.BUGCORPUS_CACHE_DIR;
    process.env.BUGCORPUS_CACHE_DIR = mkdtempSync(`${tmpdir()}/bc-empty-`);
    try {
      await hook({}, { cwd: "/tmp", ui: s.pi.ui });
    } finally {
      if (prev === undefined) delete process.env.BUGCORPUS_CACHE_DIR;
      else process.env.BUGCORPUS_CACHE_DIR = prev;
    }
    expect(s.notes).toEqual([]);
  }, 120000);

  test("session_switch warns human-only on cached newer version", async () => {
    const s = stub();
    load(s);
    const hook = s.handlers.get("session_switch");
    if (!hook) throw new Error("session_switch handler not registered");
    const dir = mkdtempSync(`${tmpdir()}/bc-update-`);
    mkdirSync(join(dir, "bugcorpus"), { recursive: true });
    writeFileSync(
      join(dir, "bugcorpus", "update.json"),
      JSON.stringify({ latest: "99.0.0", checkedAt: Date.now() / 1000 }),
    );
    // Hide any installed `bugcorpus` (a stale tool lacks update-check and
    // fails open): keep only uv + system dirs so the `uv run` fallback
    const uvDir = dirname(execFileSync("which", ["uv"]).toString().trim());
    const emptyBin = mkdtempSync(`${tmpdir()}/bc-emptybin-`);
    const repo = new URL("../..", import.meta.url).pathname.replace(/\/$/, "");
    const prevPath = process.env.PATH;
    const prevCache = process.env.BUGCORPUS_CACHE_DIR;
    process.env.PATH = `${emptyBin}:${uvDir}:/usr/bin:/bin`;
    process.env.BUGCORPUS_CACHE_DIR = dir;
    try {
      await hook({}, { cwd: repo, ui: s.pi.ui });
    } finally {
      if (prevPath === undefined) delete process.env.PATH;
      else process.env.PATH = prevPath;
      if (prevCache === undefined) delete process.env.BUGCORPUS_CACHE_DIR;
      else process.env.BUGCORPUS_CACHE_DIR = prevCache;
    }
    expect(s.notes.join("\n")).toContain("outdated");
  }, 120000);
});
