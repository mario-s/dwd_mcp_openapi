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
Use the [hyper-mcp-remote](https://github.com/hyper-mcp-rs/hyper-mcp-remote) bridge
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
## Skills
This repository contains a sample skill for agents to convert a GPX file into a KML File with enhanced weather data for specific points.