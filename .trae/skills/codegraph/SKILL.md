---
name: "codegraph"
description: "Code intelligence over a local knowledge graph: search, callers/callees, impact, trace, explore. Invoke on 'how does X work', 'who calls Y', 'blast radius of Z', or architecture/onboarding in a .codegraph/ project."
---

# CodeGraph

CodeGraph is a **local, SQLite-backed knowledge graph** of the workspace — symbols, call edges, imports, and file structure — exposed both as an MCP server (`codegraph serve --mcp`) and as a CLI (`codegraph`). It is the **pre-built search index** for an AI coding agent: 100% local, no API keys, and the upstream benchmarks show it cuts ~62% of tool calls vs. grep+Read exploration.

> Treat `codegraph_*` tool output as **already read**. Do not re-verify with grep. Reach for raw `Read`/`Grep` only for a specific detail the graph didn't cover.

## When to invoke

Trigger the `codegraph_*` MCP tools (or fall back to the `codegraph` CLI when MCP isn't connected) whenever the user asks things like:

- "How does X work / reach Y / get to Z" — architecture, request flow, runtime path.
- "What calls / uses / imports X" — callers, dependencies, blast radius.
- "What does X call / depend on" — callees, downstream.
- "What would changing X break" — impact analysis **before** refactor.
- "Find the symbol / function / class named X" — search by name.
- "Show me the source of X" (one symbol) or "show me several related symbols" (many).
- "What's in directory X / project structure" — `codegraph_files`.
- "Is the index fresh / pending sync / how big is it" — `codegraph_status`.
- After any code edit, the **staleness banner** on a `codegraph_*` response may ask you to `Read` the freshly-edited file directly.

If `.codegraph/` is missing, **offer to run `codegraph init -i`** (CLI) before answering, instead of falling back to grep.

## Tool selection (one tool per intent)

| Intent | Tool | One-liner |
|---|---|---|
| Find a symbol by name | `codegraph_search` | full-text + name match across the index |
| Map an area / "what's the deal with…" | `codegraph_context` | composes search + node + callers + callees in **one** call |
| Trace a call path X → Y | `codegraph_trace` | one call returns the whole path, incl. dynamic-dispatch hops (callbacks, React re-render, JSX children) |
| What calls this? | `codegraph_callers` | reverse call graph |
| What does this call? | `codegraph_callees` | forward call graph |
| Refactor blast radius | `codegraph_impact` | transitive impact set with depth limit |
| One symbol's source / signature / docstring | `codegraph_node` | single node |
| Survey several related symbols | `codegraph_explore` | grouped by file, **ONE capped call** — preferred over many `codegraph_node` |
| Directory / file structure | `codegraph_files` | faster than `ls` / `Glob` |
| Index health | `codegraph_status` | freshness, pending sync, counts |

## Common chains

- **Architecture / "how does X reach Y"** → `codegraph_trace` (X → Y) **first**; then ONE `codegraph_explore` for the hop bodies. Do **not** reconstruct the path with `search` + `callers` — that's exactly what `trace` does in a single call.
- **Onboarding** → `codegraph_context` first; if still unclear, `codegraph_explore` for breadth, then `codegraph_node` on specific symbols.
- **Refactor planning** → `codegraph_search` → `codegraph_callers` → `codegraph_impact`. Trust `impact` for blast radius; don't walk callers manually.
- **Debugging a regression** → `codegraph_callers` of the suspected symbol; widen with `codegraph_impact` if an unexpected call appears.

## Anti-patterns

- **Don't grep first** when looking up a symbol by name — `codegraph_search` is faster and returns kind + location + signature.
- **Don't re-verify** CodeGraph results with grep — they come from a full AST parse (tree-sitter).
- **Don't loop** `codegraph_node` over many symbols — use `codegraph_explore` once.
- **Don't chain** `codegraph_search` + `codegraph_node` when you just want context — `codegraph_context` is one round-trip.
- **Don't delegate** a "how does X work" lookup to a sub-agent that will Read files. The agent should answer directly with 2–3 `codegraph_*` calls.
- **Don't answer the same question twice** — if the graph already returned the answer, treat the response as authoritative and stop.

## CLI fallback (when MCP is unavailable)

```bash
codegraph init -i                  # initialize + build index
codegraph index [path]             # full (re)index
codegraph sync [path]              # incremental update
codegraph status [path]            # freshness + counts
codegraph query <symbol>           # search
codegraph files [path]             # file structure
codegraph context <task>           # build context for an LLM
codegraph callers <symbol>         # reverse calls
codegraph callees <symbol>         # forward calls
codegraph impact <symbol>          # blast radius
codegraph affected <files...>      # affected tests (also: --stdin)
codegraph serve --mcp              # start MCP server
```

`codegraph affected` traces import dependencies transitively to find which tests run against changed source files — pipe from `git diff --name-only | codegraph affected --stdin --quiet` and pass the result to `vitest run`.

## After an edit

- The file watcher (FSEvents / inotify / ReadDirectoryChangesW) re-syncs with a default 2 s debounce; the index lags writes by ~1 s.
- If a `codegraph_*` response starts with a `⚠️` banner naming pending files, `Read` **only those specific files** for live content. Files **not** in the banner are still fresh — keep trusting the graph.
- `codegraph_status` lists every pending file under `### Pending sync:`.

## Limitations

- Cross-file resolution is **best-effort name matching** — ambiguous calls may return multiple candidates; pick the one that fits the surrounding context.
- Not a correctness oracle — the TS compiler / test suite / linter still own that. CodeGraph adds structural context they don't have.
- Default-excluded dirs (no `.gitignore` needed): `node_modules`, `vendor`, `dist`, `build`, `target`, `.venv`, `Pods`, `.next`, files > 1 MB. To include something, add a negation to `.gitignore` (e.g. `!vendor/`).
- Sandboxed / network-share / WSL2 `/mnt` filesystems may need manual `codegraph sync`; on WSL2 `/mnt` SQLite can't always open WAL, which can cause "database is locked".
- 20+ languages supported (TS, JS, Python, Go, Rust, Java, C#, PHP, Ruby, C/C++, ObjC, Swift, Kotlin, Scala, Dart, Lua, Luau, Svelte, Vue, Liquid, Pascal). Framework-aware route recognition covers 14 web frameworks (Django, Flask, FastAPI, Express, NestJS, Laravel, Drupal, Rails, Spring, Gin, Axum, ASP.NET, Vapor, React Router / SvelteKit) plus React Native / Expo / Swift↔ObjC bridging.

## Reference

- Upstream repo: <https://github.com/colbymchenry/codegraph>
- Local clone in this workspace: `e:\code\codegraph_tmp`
- Single source of truth for tool guidance: `src/mcp/server-instructions.ts` in the upstream repo
- Docs site: <https://colbymchenry.github.io/codegraph/>
