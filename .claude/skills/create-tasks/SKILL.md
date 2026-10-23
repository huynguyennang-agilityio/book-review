---
name: create-tasks
description: Use when the user asks to "create task", "chia task", "tạo task", "break the plan into tasks", or gives a plan Artifact link (usually made by create-plan) and wants it split into tasks. Reads the plan artifact, checks it against the code, and returns an ordered task list as an Artifact plus a compact list in chat that can be passed straight to the doing-tasks skill. Does not write code.
---

# Split a plan Artifact into tasks

Write the artifact and the reply in the user's language (Huy writes Vietnamese, so use Vietnamese for him). Code, commands and file names stay as they are.

## Input

- A plan Artifact link (claude.ai/artifact/... or claude.ai/code/artifact/...). Read it with `Artifact` `action: "read"`, never WebFetch.
- No link given: use the plan published most recently in this conversation; otherwise `Artifact` `action: "list"` and pick the newest plan (title/file `plan-*`). Only ask if there are several plausible candidates.

## Process

1. **Read the plan**: recommended solution, implementation steps, decisions, expected results. If the plan still has open decisions, take the recommended option and note it under "Assumptions".
2. **Check against the code**: open the files/modules the plan names (CLAUDE.md, `docs/`, the actual code) so each task points at real paths. Flag anything in the plan that no longer matches the code.
3. **Split into tasks**. Each task:
   - fits in **one PR** (roughly < 400 changed lines, one clear purpose), with its own tests, and leaves `main` green on its own;
   - is ordered so dependencies come first; avoid tasks that touch the same files in parallel.
4. **Publish the artifact** (load `artifact-design` or run `Artifact` `quickstart` `intent: "other"` first). Source file in the scratchpad, named `tasks-<short-name>.html`; when re-splitting the same plan, republish the same file.
5. **Reply briefly**: the link, number of tasks, what needs the user (keys, decisions), and the compact list below so the user can paste it into doing-tasks. Do not start implementing.

## Per-task fields (in the artifact)

| Field | Content |
|---|---|
| ID | `T1`, `T2`, ... |
| Title | short imperative |
| Goal | 1–2 sentences: what changes and why |
| Files | files/modules to change or add |
| Depends on | task IDs or "—" |
| Needs from user | key/env var (name only), billing, decision, paid run — or "—" |
| Done when | tests/lint/mypy green + concrete check (script output, behaviour) |
| Size | S / M / L |
| Eval | "no" by default; mark "eval later (local, on request)" if the plan expects one |

Also include at the top: plan link, assumptions, and a summary table (ID, title, depends on, needs from user). At the end: risks and anything in the plan that was dropped or deferred.

## Compact list for chat

```
Plan: <plan link> · Tasks: <tasks artifact link>
T1. <title> — <files> (deps: —)
T2. <title> — <files> (deps: T1) [cần: GOOGLE_API_KEY]
...
```

## Notes

- Never put key values in the artifact; env var names only.
- Don't invent work the plan doesn't ask for; put good-to-have extras in a separate "Optional" section.
