"""MCP Server Bridge for DWD NWP EDR API."""

from __future__ import annotations

import json
from typing import Any, Optional
from mcp.server.mcpserver import MCPServer
from dwd_client import DwdEdrClient, DEFAULT_COLLECTION

server = MCPServer(name="dwd-mcp-server")
client = DwdEdrClient()


@server.tool(
    name="get_dwd_api_info",
    description="Get general API information and landing page links from the DWD EDR API.",
)
async def get_dwd_api_info() -> str:
    """Get general API information and landing page links from the DWD EDR API."""
    data = await client.get_landing_page()
    return json.dumps(data, indent=2)


@server.tool(
    name="list_model_collections",
    description="List all available weather model data collections in DWD EDR API (e.g. ICON-D2-RUC@single_level).",
)
async def list_model_collections() -> str:
    """List all available weather model data collections in DWD EDR API."""
    collections = await client.list_collections()
    return json.dumps(collections, indent=2)


@server.tool(
    name="describe_model_collection",
    description="Get metadata for a specific model collection, including available parameter names and query types.",
)
async def describe_model_collection(collection_id: str = DEFAULT_COLLECTION) -> str:
    """Get metadata for a specific model collection.

    Args:
        collection_id: The collection ID (default: ICON-D2-RUC@single_level).
    """
    metadata = await client.get_collection(collection_id)
    return json.dumps(metadata, indent=2)


@server.tool(
    name="list_model_run_instances",
    description="List all available model run instances (forecast reference runs) for a collection.",
)
async def list_model_run_instances(collection_id: str = DEFAULT_COLLECTION) -> str:
    """List all available model run instances (forecast reference runs) for a collection.

    Args:
        collection_id: The collection ID (default: ICON-D2-RUC@single_level).
    """
    instances = await client.list_instances(collection_id)
    return json.dumps(instances, indent=2)


@server.tool(
    name="get_point_weather_forecast",
    description="Get a high-level parsed weather forecast time series for a specific location (lat/lon).",
)
async def get_point_weather_forecast(
    latitude: float,
    longitude: float,
    collection_id: str = DEFAULT_COLLECTION,
    instance_id: Optional[str] = None,
    parameters: Optional[list[str]] = None,
    datetime_range: Optional[str] = None,
) -> str:
    """Get a high-level parsed weather forecast time series for a specific location (lat/lon).

    Returns temperature in Celsius & Kelvin, precipitation, wind components (U_10M, V_10M),
    cloud cover, pressure, etc. across forecast time steps.

    Args:
        latitude: Latitude coordinate in degrees (e.g. 52.52 for Berlin, 50.11 for Frankfurt).
        longitude: Longitude coordinate in degrees (e.g. 13.405 for Berlin, 8.68 for Frankfurt).
        collection_id: Model collection name (default: ICON-D2-RUC@single_level).
        instance_id: Specific model run instance timestamp (default: latest available run).
        parameters: Specific parameter names to query (e.g. ['T_2M', 'TOT_PREC', 'U_10M', 'V_10M', 'CLCT']).
        datetime_range: Optional ISO8601 time string or interval (e.g. '2026-09-24T08:00:00Z/2026-09-24T18:00:00Z').
    """
    forecast = await client.get_point_forecast(
        latitude=latitude,
        longitude=longitude,
        collection_id=collection_id,
        instance_id=instance_id,
        parameters=parameters,
        datetime_range=datetime_range,
    )
    return json.dumps(forecast, indent=2)


@server.tool(
    name="query_edr_position",
    description="Query DWD EDR API position endpoint (WKT POINT coordinates) returning raw coverage data.",
)
async def query_edr_position(
    coords: str,
    collection_id: str = DEFAULT_COLLECTION,
    instance_id: Optional[str] = None,
    parameter_names: Optional[str] = None,
    datetime_val: Optional[str] = None,
    crs: Optional[str] = None,
    output_format: str = "CoverageJSON",
) -> str:
    """Query DWD EDR API position endpoint (WKT POINT coordinates) returning raw coverage data.

    Args:
        coords: WKT Point string, e.g. 'POINT(13.4050 52.5200)' (longitude latitude format).
        collection_id: Model collection ID.
        instance_id: Optional model run instance ID.
        parameter_names: Comma-separated parameter names (e.g. 'T_2M,TOT_PREC').
        datetime_val: ISO8601 timestamp or range string.
        crs: Coordinate reference system identifier.
        output_format: Output format, e.g. CoverageJSON.
    """
    data = await client.get_position_raw(
        collection_id=collection_id,
        coords=coords,
        instance_id=instance_id,
        parameter_names=parameter_names,
        datetime_val=datetime_val,
        crs=crs,
        output_format=output_format,
    )
    return json.dumps(data, indent=2)


@server.tool(
    name="query_edr_radius",
    description="Query DWD EDR API radius endpoint returning coverage data around a center coordinate.",
)
async def query_edr_radius(
    coords: str,
    within: float,
    within_units: str = "km",
    collection_id: str = DEFAULT_COLLECTION,
    instance_id: Optional[str] = None,
    parameter_names: Optional[str] = None,
    datetime_val: Optional[str] = None,
    crs: Optional[str] = None,
    output_format: str = "CoverageJSON",
) -> str:
    """Query DWD EDR API radius endpoint returning coverage data around a center coordinate.

    Args:
        coords: Center point WKT string, e.g. 'POINT(13.4050 52.5200)'.
        within: Radius distance.
        within_units: Units for radius ('km', 'm', 'mi', etc.).
        collection_id: Model collection ID.
        instance_id: Optional model run instance ID.
        parameter_names: Comma-separated parameter names.
        datetime_val: ISO8601 timestamp or range string.
        crs: Coordinate reference system identifier.
        output_format: Output format, e.g. CoverageJSON.
    """
    data = await client.get_radius_raw(
        collection_id=collection_id,
        coords=coords,
        within=within,
        within_units=within_units,
        instance_id=instance_id,
        parameter_names=parameter_names,
        datetime_val=datetime_val,
        crs=crs,
        output_format=output_format,
    )
    return json.dumps(data, indent=2)


@server.tool(
    name="query_edr_area",
    description="Query DWD EDR API area endpoint (WKT POLYGON coordinates).",
)
async def query_edr_area(
    coords: str,
    collection_id: str = DEFAULT_COLLECTION,
    instance_id: Optional[str] = None,
    parameter_names: Optional[str] = None,
    datetime_val: Optional[str] = None,
    crs: Optional[str] = None,
    output_format: str = "CoverageJSON",
) -> str:
    """Query DWD EDR API area endpoint (WKT POLYGON coordinates).

    Args:
        coords: WKT Polygon string, e.g. 'POLYGON((13.3 52.4, 13.5 52.4, 13.5 52.6, 13.3 52.6, 13.3 52.4))'.
        collection_id: Model collection ID.
        instance_id: Optional model run instance ID.
        parameter_names: Comma-separated parameter names.
        datetime_val: ISO8601 timestamp or range string.
        crs: Coordinate reference system identifier.
        output_format: Output format, e.g. CoverageJSON.
    """
    data = await client.get_area_raw(
        collection_id=collection_id,
        coords=coords,
        instance_id=instance_id,
        parameter_names=parameter_names,
        datetime_val=datetime_val,
        crs=crs,
        output_format=output_format,
    )
    return json.dumps(data, indent=2)


@server.tool(
    name="query_edr_cube",
    description="Query DWD EDR API cube endpoint for bounding box volume.",
)
async def query_edr_cube(
    bbox: str,
    collection_id: str = DEFAULT_COLLECTION,
    instance_id: Optional[str] = None,
    parameter_names: Optional[str] = None,
    datetime_val: Optional[str] = None,
    crs: Optional[str] = None,
    output_format: str = "CoverageJSON",
) -> str:
    """Query DWD EDR API cube endpoint for bounding box volume.

    Args:
        bbox: Bounding box string 'minx,miny,maxx,maxy' (e.g. '13.3,52.4,13.5,52.6').
        collection_id: Model collection ID.
        instance_id: Optional model run instance ID.
        parameter_names: Comma-separated parameter names.
        datetime_val: ISO8601 timestamp or range string.
        crs: Coordinate reference system identifier.
        output_format: Output format, e.g. CoverageJSON.
    """
    data = await client.get_cube_raw(
        collection_id=collection_id,
        bbox=bbox,
        instance_id=instance_id,
        parameter_names=parameter_names,
        datetime_val=datetime_val,
        crs=crs,
        output_format=output_format,
    )
    return json.dumps(data, indent=2)


def main() -> None:
    """Run the MCPServer."""
    ## stdio
    ## server.run()

    ## streamable
    server.run(transport="streamable-http", host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
