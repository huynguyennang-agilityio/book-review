---
name: create-plan
description: Use whenever the user asks to "make a plan", "create a plan", "plan this", "lên plan", "lập kế hoạch", or asks how a feature or bug fix should be done. The result is always an Artifact (HTML page) with requirements, solutions, technical details, implementation steps and expected results, plus a short reply with the link. Do not write code until the user approves the plan.
---

# Create a plan as an Artifact

Write the artifact and the reply in the user's language (Huy writes Vietnamese, so use Vietnamese for him). Code, commands and file names stay as they are.

## Process

1. **Understand the ask**: read the user's message and related context (thread, CLAUDE.md, memory). If one point is unclear, pick a sensible default and record it under "Assumptions"; only ask when the choice would change the goal itself.
2. **Investigate for real**: read the relevant code, logs and data. Every claim in the plan needs evidence (`file:line`, measured numbers, logs) or is explicitly marked as inferred.
3. **Write the artifact** using the structure below. Before writing, call `Artifact` with `action: "quickstart"`, `intent: "other"` (or load the `artifact-design` skill) and follow its design guidance. Put the source file in the scratchpad, named `plan-<short-name>.html`. When updating an existing plan, republish the same file/URL instead of creating a new artifact.
4. **Reply briefly**: 2–4 lines with the artifact link, the recommended solution, any decision the user must make, then ask whether they approve so you can start step 1. Do not paste the plan content into the reply.
5. **No code** until the user approves. When implementation starts, if the repo has a convention for storing plans (e.g. `docs/plan/<feature>/`), copy the plan there in the first PR.

## Artifact structure (all 5 main sections, in this order)

1. **Requirements**
   - The problem in the user's words, current state (the issue being hit, with numbers if available), scope and out of scope, assumptions.
2. **Solutions**
   - 2–3 options. For each: short description, pros, cons, cost (API spend, build time), risks.
   - A comparison table of the options; clearly mark the **recommended option** and why.
3. **Technical details** (for the recommended option)
   - Files/modules to change or add, data flow (a simple diagram if it helps), config/env/schema/migration changes, new libraries, how it will be tested.
4. **Implementation steps**
   - Numbered steps, each sized as one small PR with tests: what is done, output, definition of done. Include a time estimate.
   - Mark separately any step that needs the user (adding a key, enabling billing, agreeing to run a paid eval).
5. **Expected results**
   - Measurable completion criteria (numbers before → after, green tests, video meets the bar...), how to verify, expected cost.

Add at the end when relevant: **Risks & mitigations**, **Decisions needed** (questions answerable in one word, with a recommended option).

## Notes

- Keep it short and skimmable: clear headings, tables, bullet points; don't replay the investigation.
- Don't invent numbers or prices; cite the source for prices, mark unchecked ones "unverified".
- The artifact must not contain keys, tokens or secret data.
