# Canvas Plugin Lab Guidance

- This repo is only for Canvas Medical plugin work.
- Use `$canvas-plugin-assistant` for plugin design, implementation, deploy, and review workflows.
- Keep one plugin per directory under `plugins/`.
- Use `uv run ...` for Python tooling and `uv run python ...` for scripts. Do not use bare `python` or `pip`.
- Write or update `plugin-spec.md` before scaffolding or major behavior changes.
- Never commit credentials, plugin secret JSON, or instance-specific secrets.
- Ask before any deploy or log access against a real Canvas instance.
