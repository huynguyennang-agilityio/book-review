---
name: doing-tasks
description: Use when the user says "doing tasks", "làm task", "làm các task này", "do these tasks", or gives a task list (pasted text or a tasks Artifact link from create-tasks) to implement. Orders the tasks, reports up front everything that needs the user (keys, decisions), then implements every task end to end — branch, code, tests, PR, wait for green CI, merge — without asking along the way. Does not run evals unless the user says so. At the end publishes one Artifact listing any issues for the user to review.
---

# Implement a task list end to end

Reply in the user's language (Huy writes Vietnamese). Follow the repo's CLAUDE.md (commands, where scripts run, merge rules). Ask as little as possible.

## Input

- Pasted task list, or a tasks Artifact link (read with `Artifact` `action: "read"`). If the tasks reference a plan artifact, read it too for context.

## 1. Prepare (one message to the user, then keep going)

1. **Order** the tasks by dependency, then by risk (foundations and refactors first, UI/docs last). Merge tasks that are too small to stand alone; split ones too big for one PR.
2. **Pre-flight check** everything that could block:
   - env vars the tasks need: check only that the **name** exists in `.env` (e.g. `grep -c '^GOOGLE_API_KEY=' .env`); never print or log values;
   - services (docker compose, Postgres, Redis), `gh auth status`, clean git tree on an up-to-date `main`;
   - decisions the task list left open.
3. **Report once**: the ordered list, plus a short "Cần anh/chị" list (missing keys, decisions). For open decisions, take the recommended/default option and say so instead of waiting. Then **start right away** with the tasks that are not blocked; only blocked tasks wait for the user's answer.

## 2. Each task (loop, no check-ins)

1. `git switch main && git pull`, then a branch `claude/<short-task-name>`.
2. Implement, matching the surrounding code style. Add/update tests.
3. Run the repo's checks (here: `uv run pytest`, `uv run ruff check . && uv run ruff format --check . && uv run mypy`; `pnpm` lint/test/build for `apps/web` when touched). Fix and rerun until green.
4. Run real scripts only when the task needs them to verify and they're cheap; **never run evals** (`evals/run_ragas.py` or similar paid/quota-heavy runs) unless the user explicitly asked in this session — when they do, run them locally on the Mac.
5. Commit, push, open a PR (`gh pr create`) with what/why/how tested and the task ID. Wait for CI (`gh pr checks --watch`, in the background if long). CI red → fix and push again. Green → `gh pr merge --merge --delete-branch` (the user has authorised self-merge). Never push to `main`.
6. Log in a running list: task ID, PR link, result, and any issue noted.

Stop and tell the user only for: quota / rate limit, a missing/expired key, a failure you cannot fix after a few real attempts, or a decision that changes the goal. Otherwise skip the blocked task, record it as an issue, and continue with the next one that doesn't depend on it.

## 3. Wrap up

1. If there are any issues (blocked/skipped tasks, workarounds, known bugs, tech debt, things to verify by hand, evals worth running, plan deviations), publish **one** Artifact (load `artifact-design` first; scratchpad file `issues-<short-name>.html`, republish the same file on later rounds) with:
   - summary table: task → PR (merged / not) ;
   - issues, most important first: what, where (`file:line`, PR), impact, suggested fix, what's needed from the user;
   - suggested evals/commands for the user to trigger later (not run).
2. Final reply, short: tasks done with merged PR links, script results and cost if any, then the issues artifact link and a request to review it and say what to fix. If there were no issues, say so and skip the artifact.
