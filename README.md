# dwd-mcp-server
A Python based MCP server for DWD Team "Honigbiene"
It uses the [Environmental Data Retrieval (EDR) API](https://nwp.opendata-api.dwd.de/v1beta1/docs) by Deutscher Wetterdienst (DWD).

## Requirements
It is recommended to use [uv](https://github.com/astral-sh/uv) to start the server.

## Starting
```
source .venv/bin/activate
uv run python main.py
```

## Connecting to a client
### Claude
```
  "mcpServers": {
    "dwd-weather-server": {
      "command": "hyper-mcp-remote",
      "args": [
        "--no-auth",
        "--allow-http",
        "http://127.0.0.1:8080/mcp"
      ]
    }
  }
```