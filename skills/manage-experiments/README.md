# Manage experiments

Maintain an experiment through multiple recipes, measurements and phase archives.
The Skill produces readable records and explicit material decisions; the project's
existing scientific tools still perform the experiment.

Ask, for example: “Inventory this experiment's outputs, show what should stay
remote and what is useful locally, then archive the agreed phase.” A read-only
comparison alone belongs to `review-experiments`.

Start with `SKILL.md`. The shared experiment contract provides a flexible file
example and required record contents. The optional standard-library helper prints
an exact file preview and verifies that it has not changed; it never transfers or
deletes files. SSH, native file operations and Git retain their normal boundaries.
No service, frontend, model call or extra Python dependency is required.
