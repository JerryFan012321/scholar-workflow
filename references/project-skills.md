# Project Skills and Installed Research Skills

Use when creating project-specific skills or deciding which layer owns a requested
operation. This contract does not create skills, migrate a project or authorize
execution. Preserve the existing project identity, instructions and accepted formats.

## Three separate layers

| Layer | Owns | Distribution boundary |
|---|---|---|
| Plugin development | Scholar Workflow implementation, developer backlog, tests and release work | Development checkout only; not installed as research skills |
| Generic research runtime | Reusable research operations, supported CLI interfaces and accepted output contracts | The installed plugin's `skills/` and runtime references |
| Research project | That project's rules, scientific operations, selected resources and acceptance conditions | The project's own `.agents/skills/`; never added to the generic plugin merely because one project needs it |

Canonical project rules remain in `AGENTS.md`; host entry points only reference
them. `PROJECT.md` owns the internal situation and navigation, with one detailed
plan in PROJECT, the selected SCHEDULE or the existing plan authority. A skill is
not a second plan, experiment ledger, server list or conversation-memory store.

## Management and execution are different tasks

Generic `init-project` creates the declared skeleton, `organize-project` presents
selected project context, and `review-experiments` explains selected existing
results. These management capabilities do not run an experiment or manufacture
missing execution records. Existing record/collection commands retain their own
explicit write boundaries.

A project-specific **execution skill** describes a recurring operation of that
project: for example, its actual baseline reproduction, data preparation or
evaluation entry. It identifies the applicable child, real config/CLI inputs,
required environment, produced Run/Attempt evidence and task-specific acceptance
conditions. It uses the project's actual operations rather than a copied generic
example. New commands must exist before the skill advertises them.

A project-specific **management skill** is warranted only when a recurring local
management operation needs information or a workflow absent from the generic
capabilities. It supplies those project-specific facts and reuses the generic
document/record contracts. Do not create one skill for each plan item or scientific
stage, or duplicate the general PROJECT, paper or experiment-review templates.

## Adding a project skill

For an explicitly requested reusable project operation, inspect existing project
skills and public entries before proposing the smallest necessary addition. Use
`.agents/skills/<task-name>/SKILL.md`, with a concise `name` and discriminating
`description`; add scripts, references or assets only when the operation needs them.
Do not install it globally, add host-specific copies or generate placeholder skills
as an initialization side effect. Existing projects keep their current files until
a selected change is requested.

The skill's observable contract covers the applicable items below:

- Project/child identity, selected operation and authorized filesystem/host scope.
- Real inputs, editable config and supported overrides; refer to canonical project
  configs instead of embedding a second mutable recipe in the skill.
- For a fixed operation, its actual prerequisites, dependent actions, failure/stop
  conditions and handoffs. Exploration has no prescribed thinking sequence.
- Outputs, original record locations, accepted presentation contract and the
  evidence needed to distinguish execution, collection and analysis completion.
- Human assessment still required, with the object, opening method and judgment
  criteria stated in the conversation.

Only project-specific facts and actual operation details belong in that skill.
Use the installed plugin's applicable runtime reference for shared formats rather
than copying it. Record the contract/interface actually needed when compatibility
matters; resolve its installed location at use time, without hardcoding a cache
version, developer checkout, personal path or model. Missing/incompatible required
interfaces are an explicit gap, not permission to rewrite old outputs.

## Parent and remote-child cooperation

The local research parent keeps overall plans, knowledge and analysis. Each remote
execution child keeps its own source/config operations and applicable local skills
under its independent Git. `primary` follows the same boundary. Share selected
project rules or references through an explicit task handoff; do not duplicate all
parent skills, knowledge or session history into every child.

Before remote execution, confirm that the selected skill, runtime support and
dependencies are actually available in that environment. A local plugin install
does not install remote skills or grant SSH/Git access. Native SSH/Remote-SSH and
cmux retain their own permissions and session/window behavior; Hub, workspace
registration, a browser, a fixed port or a new worker is never a prerequisite.

The parent initiates selected result collection under
[project-management.md](project-management.md). Execution skills leave original
records in the child and report what is ready to pull; read-only management skills
do not collect. The parent retains human-readable evidence, not model payloads, and
keeps missing transfer/export support visible.

## Existing contract authorities

- [project-entry.md](project-entry.md): internal PROJECT, unique plan and lightweight
  project literature; public README remains separate.
- [project-context.md](project-context.md): selected code, papers and experiment
  references; paper units retain their existing owners and complete assets.
- [asset-units.md](asset-units.md): complete paper, blog and document units are the
  management objects; their existing identities and owners remain authoritative.
- [experiment-review.md](experiment-review.md): explicit conditions beside results,
  explanatory reports and selected evidence.
- [project-management.md](project-management.md): parent/child identity, remote
  source development, local collection and recovery boundaries.

Paper prose, Canvas, excerpts and figures continue to use their owning analysis
contract; a project skill cannot simplify those accepted formats. Servers,
knowledge registrations, research-channel subscriptions and author watchlists
retain their respective stores; this skill layering creates no central registry.
