// OMP extension contract: registers commands once, hooks cheap, fails open.
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
  test("registers three commands and one hook, once across double load", () => {
    const s = stub();
    load(s);
    load(s);
    expect([...s.commands.keys()]).toEqual(["bug-corpus", "bug-learn", "bug-scan"]);
    expect([...s.handlers.keys()]).toEqual(["tool_result"]);
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
    const repo = new URL("../../..", import.meta.url).pathname.replace(/\/$/, "");
    const out = await hook(
      { toolName: "edit", input: { path: `${repo}/bugcorpus/cli.py` }, content: [] },
      { cwd: repo },
    );
    expect(out).toBeUndefined(); // no findings in cli.py -> silent
  }, 120000); // nested `uv run` under pytest contends the uv lock; extension caps at 30s
});
