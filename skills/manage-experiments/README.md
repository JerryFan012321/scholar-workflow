# Manage experiments

Maintain an experiment through multiple recipes, measurements and phase archives.
The Skill produces readable records and explicit material decisions; the project's
existing scientific tools still perform the experiment.

Recipes/code remain lightweight and assets are referenced. At each archive point,
select individual recipe versions and results, verify their dependencies, then clear
unretained intervening recipes/results and intermediates. Git preserves light history;
the operation does not create another complete output snapshot.

Ask, for example: “Inventory this experiment's outputs, show what should stay
remote and what is useful locally, then archive the agreed phase.” A read-only
comparison alone belongs to `review-experiments`.

Start with `SKILL.md`. The shared experiment contract provides a flexible file
example and required record contents. The optional standard-library helper prints
an exact file preview and verifies that it has not changed; it never transfers or
deletes files. SSH, native file operations and Git retain their normal boundaries.
No service, frontend, model call or extra Python dependency is required.

Shared model/data inputs and reusable results follow the
[workspace asset pool contract](../../references/workspace-assets.md). Recipes refer
to exact asset versions and read-only execution reuses them without copying inputs.
Changes to asset content use a writable derivative; registration and selected transfers
have separate scopes. The material helper is not an asset-ID resolver.
