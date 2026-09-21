# HomeControll

Home automation / control project. **Greenfield** — no application code exists yet.
Development is driven by [GitHub Spec Kit](https://github.com/github/spec-kit):
specification first, then plan, then tasks, then implementation.

## Spec-driven workflow

Do not write feature code before a spec exists. The pipeline, in order:

| Step | Skill | Produces |
|------|-------|----------|
| 1 | `/speckit-constitution` | `.specify/memory/constitution.md` — project principles |
| 2 | `/speckit-specify` | `specs/<nnn>-<slug>/spec.md` — what & why, no tech choices |
| 3 | `/speckit-clarify` *(optional)* | resolves ambiguities in the spec before planning |
| 4 | `/speckit-plan` | `plan.md` + design docs — how, incl. tech choices |
| 5 | `/speckit-tasks` | `tasks.md` — ordered, actionable work items |
| 6 | `/speckit-analyze` *(optional)* | cross-artifact consistency report |
| 7 | `/speckit-implement` | the actual code, task by task |

`/speckit-checklist` generates quality checklists after planning.
`/speckit-converge` assesses existing code and appends remaining work as tasks.

Each feature gets its own git branch and its own `specs/<nnn>-<slug>/` directory,
both created by `.specify/scripts/bash/create-new-feature.sh`. Let the skills call
the scripts — don't hand-create spec directories.

## Repository layout

```
.specify/
  memory/constitution.md   project principles — read before planning
  templates/               spec, plan, tasks, checklist templates
  scripts/bash/            helper scripts invoked by the skills
.claude/skills/speckit-*/  the spec-kit skills themselves
specs/<nnn>-<slug>/        one directory per feature (created on demand)
```

Treat `.specify/templates/` and `.specify/scripts/` as vendored: change them only
deliberately, since `specify init` overwrites them on upgrade.

## Conventions

- Branch per feature, named after the spec directory (e.g. `001-device-registry`).
- Specs describe user-visible behavior and requirements; technology decisions
  belong in `plan.md`, not in `spec.md`.
- Keep the constitution current — the planning and analysis skills check against it.

## Stack

Not chosen yet. Record the decision in the constitution and the first feature's
`plan.md`, then replace this section with build, test, and run commands.
