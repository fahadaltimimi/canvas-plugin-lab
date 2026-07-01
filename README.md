# Canvas Plugin Lab

Dedicated sandbox repo for Canvas Medical plugin design, implementation, and testing with Codex.

This repo is intentionally separate from `patient-portal` so Canvas-specific credentials, CLI workflows, Python tooling, and deployment notes do not leak into unrelated application work.

## Repo Layout

- `plugins/` - one directory per Canvas plugin under active development
- `docs/specs/` - approved specs and design notes before or alongside scaffolding

## Local Prerequisites

- Python 3.12+
- `uv`
- Canvas CLI
- Local credentials at `~/.canvas/credentials.ini`

## Operating Rules

- Use the personal Codex skill `$canvas-plugin-assistant` for Canvas plugin authoring workflows.
- Use `uv run ...` for Python tooling and `uv run python ...` for scripts.
- Write or update `plugin-spec.md` before major implementation.
- Never commit credentials, plugin secret JSON, or instance-specific secrets.

## Suggested Workflow

1. Start with a design prompt using `$canvas-plugin-assistant`.
2. Write and approve `plugin-spec.md`.
3. Scaffold the plugin under `plugins/<plugin-name>/`.
4. Implement the smallest useful behavior first.
5. Deploy and tail logs only when you are ready for real-instance testing.

## Prompt Starters

- `Use $canvas-plugin-assistant to check whether this repo is ready for Canvas plugin development.`
- `Use $canvas-plugin-assistant to turn this idea into a plugin-spec.md before we scaffold anything.`
- `Use $canvas-plugin-assistant to review this existing Canvas plugin and prepare a safe deploy/UAT plan.`
