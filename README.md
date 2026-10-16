# quality-assurance

Pixi-first quality assessment MCP server: lint, type-check, security, complexity, baselines and trend analysis behind a lean 3-meta-tool interface.

## Overview

`quality-assurance` is an MCP server (package `src/quality_assurance`) that runs quality tooling through pixi and returns compact, structured results. The lean server (`quality_assurance.lean_server`) exposes only `discover_tools`, `get_tool_spec` and `execute_tool` to keep client context small; the HTTP transport (`quality_assurance.http_lean_server`) serves it on port **4106** at `http://127.0.0.1:4106/mcp`.

Tools reachable through `execute_tool`:

- Assessment: `quality_execute_lint_assessment`, `quality_execute_typecheck_assessment`, `quality_execute_security_scan`, `quality_execute_complexity_analysis`, `quality_execute_comprehensive_suite`
- Analysis: `quality_calculate_quality_score`, `quality_generate_recommendations`, `quality_detect_quality_patterns`, `quality_prioritize_issues`
- Baselines and trends: `quality_establish_baseline`, `quality_compare_against_baseline`, `quality_analyze_trends`
- Fixes and reports: `quality_apply_automated_fixes`, `quality_generate_comprehensive_report`
- Pixi integration: `quality_execute_pixi_aware_assessment`, `quality_optimize_pixi_environment`, `quality_generate_pixi_tasks`, `quality_validate_pixi_integration`
- Health: `quality_get_system_health`

See [LEAN_MCP_IMPLEMENTATION.md](LEAN_MCP_IMPLEMENTATION.md) for the lean protocol details.

## Development

This project is pixi-only; the package installs itself editable via `[tool.pixi.pypi-dependencies]`. Do not use pip or uv directly.

```bash
pixi install -e ci

# Tests (pass -e: `test` exists in ci, py312 and py313)
pixi run -e ci test

# Lint + type-check + tests
pixi run -e ci quality

# Start the HTTP MCP server (port 4106)
pixi run http-server
```

## Available Tasks

| Task | Environment | Description |
|------|-------------|-------------|
| `test` | `ci`, `py312`, `py313` | Run the test suite on that environment's interpreter |
| `quality` | `ci` | Run `test`, `lint` and `typecheck` |
| `lint` / `lint-full` / `lint-fix` | `ci` | Ruff critical rules / all rules / auto-fix |
| `format` / `format-check` | `ci` | Ruff format / verify formatting |
| `typecheck` | `ci` | mypy over `src/` |
| `test-cov` | default | Tests with coverage (runs in `quality` env) |
| `static-analysis` | `quality-extended` | bandit, safety and radon |
| `build` | `ci` | Build the distribution |
| `http-server` | default | Start the HTTP MCP server (port 4106) |
| `lean-server` | default | Start the lean stdio MCP server |
| `server` | default | Start the full stdio MCP server |

Run `pixi task list -e <env>` for the complete list.

## Branch model

- Feature, fix and chore branches open PRs into `development` only.
- Only `development` may open a PR into `main`; the Branch Policy check enforces this.
- Required checks: **CI Success** (plus **Branch Policy** on PRs to `main`).
- No direct pushes to `development` or `main`.

## License

MIT License - see [LICENSE](LICENSE) for details.
