# CardOps — Claude Code Workflow

## Workflow orchestration

### 1. Plan mode default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- Write the plan to `tasks/todo.md` before writing a single line of code
- If something goes sideways mid-task, STOP and re-plan — do not keep pushing
- Use plan mode for verification steps, not just building
- **CardOps-specific:** any task touching the schema, ingestion pipeline, or scan pipeline requires a plan check-in regardless of size

### 2. Subagent strategy
- Use subagents to keep the main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One focused task per subagent
- For complex problems, use multiple subagents in parallel rather than one long sequential chain

### 3. Self-improvement loop
- After ANY correction from the user: update `tasks/lessons.md` immediately
- Write the pattern as a rule, not a description of the mistake
- Review `tasks/lessons.md` at the start of every session
- If the same mistake occurs twice: the lesson wasn't specific enough — rewrite it

### 4. Verification before done
- Never mark a task complete without proving it works
- For migrations: `alembic check` + query the table directly
- For API endpoints: a real HTTP request returning the expected response
- For ingestion jobs: verify row counts and spot-check data correctness
- Ask: "Would a staff engineer approve this PR?"

### 5. Demand elegance (balanced)
- For non-trivial changes: pause and ask "is there a more elegant solution?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip for simple, obvious fixes — do not over-engineer
- Challenge your own work before presenting it

### 6. Autonomous bug fixing
- When given a bug report: fix it — do not ask for hand-holding
- Point at logs, errors, failing tests and resolve them
- **Exception:** any fix requiring a schema migration, or touching the `auth` schema — flag before executing

---

## Task management

### Starting a task
1. **Plan first** — write plan to `tasks/todo.md` with checkable items
2. **Verify plan** — check in with user before implementation starts (for non-trivial tasks)
3. **Prime context** — re-read relevant spec sections and lessons before writing code

### During a task
4. **Track progress** — mark items complete in `tasks/todo.md` as you go
5. **Explain changes** — high-level summary at each meaningful step
6. **One concern at a time** — finish what you started before picking up something adjacent

### Completing a task
7. **Verify** — prove it works before marking complete (see Verification above)
8. **Document results** — add a brief results/review section at the bottom of `tasks/todo.md`
9. **Capture lessons** — update `tasks/lessons.md` with anything learned or corrected

---

## Stop conditions — always check in with user before proceeding

- Task requires a schema migration not already planned in the spec
- A fix would touch the Supabase `auth` schema
- A dependency not in the approved tech stack is needed
- A design decision conflicts with Section 10 of `CardOps-Project-Spec_v2.md`
- You are more than 2 steps into an unreviewed plan
- The scope of a task has grown significantly from the original plan

---

## Core principles

- **Simplicity first** — make every change as simple as possible; impact minimal code
- **No laziness** — find root causes; no temporary fixes; senior developer standards
- **Minimal impact** — changes should only touch what's necessary to avoid introducing bugs
- **Spec fidelity** — when in doubt, check the spec; never improvise architectural decisions
