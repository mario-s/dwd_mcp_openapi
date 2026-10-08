# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
- Python MCP server exposing DWD (Deutscher Wetterdienst) Environmental Data Retrieval (EDR) API endpoints (`https://nwp.opendata-api.dwd.de/v1beta1`).
- Package management and environment via `uv` targeting Python 3.14 (`.python-version`, `pyproject.toml`).

## Build, Run & Test Commands
- Environment sync: `uv sync`
- Run server: `uv run python main.py` or `uv run mcp dev main.py`
- Run all tests: `uv run pytest`
- Run single test file: `uv run pytest tests/test_weather.py`
- Run single test by name: `uv run pytest tests/test_weather.py -k test_function_name`
- Lint & format check: `uv run ruff check .` / `uv run ruff format --check .`
- Auto-format: `uv run ruff format .`
- MCP inspector with DWD OpenAPI bridge:
  ```bash
  npx @modelcontextprotocol/inspector npx @ivotoby/openapi-mcp-server --api-base-url https://nwp.opendata-api.dwd.de/v1beta1 --openapi-spec https://nwp.opendata-api.dwd.de/v1beta1/openapi.json
  ```

## Code & Architecture Guidelines
- **MCP Framework**: Use the official `mcp` SDK (`MCPServer`) as declared in `pyproject.toml`.
- **API Target**: DWD EDR API OpenAPI spec at `https://nwp.opendata-api.dwd.de/v1beta1/openapi.json`. Keep weather retrieval logic in [`dwd_client.py`](dwd_client.py) and MCP tool registrations / server lifecycle in [`main.py`](main.py).
- **Type Annotations**: Mandatory type hints across all tool signatures and helper functions; use Pydantic models where structured parameters or output schemas are required by MCP tools.
- **Async & Network**: Prefer async client requests (e.g., `httpx`) with strict timeouts and error handling when contacting DWD endpoints.
