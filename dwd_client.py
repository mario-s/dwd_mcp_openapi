"""DWD EDR API Client."""

from __future__ import annotations

from typing import Any, Optional
import httpx

DWD_BASE_URL = "https://nwp.opendata-api.dwd.de/v1beta1"
DEFAULT_COLLECTION = "ICON-D2-RUC@single_level"


class DwdEdrClient:
    """Client for querying the Deutscher Wetterdienst (DWD) NWP EDR API."""

    def __init__(self, base_url: str = DWD_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        # Filter None params
        query_params = {k: v for k, v in (params or {}).items() if v is not None}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=query_params, headers=headers)
            response.raise_for_status()
            return response.json()

    async def get_landing_page(self) -> dict[str, Any]:
        """Retrieve the API landing page with links to available endpoints."""
        return await self._get("/")

    async def get_conformance(self) -> dict[str, Any]:
        """Describe standards this API conforms to."""
        return await self._get("/conformance")

    async def list_collections(self) -> list[dict[str, Any]]:
        """Describe all available model data collections."""
        data = await self._get("/collections")
        return data.get("collections", [])

    async def get_collection(self, collection_id: str = DEFAULT_COLLECTION) -> dict[str, Any]:
        """Describe a specific model data collection, including its parameters and query types."""
        return await self._get(f"/collections/{collection_id}")

    async def list_instances(self, collection_id: str = DEFAULT_COLLECTION) -> list[dict[str, Any]]:
        """Describe all available model run instances for a model data collection."""
        data = await self._get(f"/collections/{collection_id}/instances")
        return data.get("instances", [])

    async def get_latest_instance_id(self, collection_id: str = DEFAULT_COLLECTION) -> str:
        """Fetch the latest available model run instance ID for a collection."""
        instances = await self.list_instances(collection_id)
        if not instances:
            raise ValueError(f"No instances available for collection {collection_id}")
        return instances[-1]["id"]

    async def get_position_raw(
        self,
        collection_id: str,
        coords: str,
        instance_id: Optional[str] = None,
        parameter_names: Optional[str] = None,
        datetime_val: Optional[str] = None,
        crs: Optional[str] = None,
        output_format: str = "CoverageJSON",
    ) -> dict[str, Any]:
        """Low-level position query returning raw CoverageJSON."""
        if instance_id:
            path = f"/collections/{collection_id}/instances/{instance_id}/position"
        else:
            path = f"/collections/{collection_id}/position"

        params = {
            "coords": coords,
            "parameter-name": parameter_names,
            "datetime": datetime_val,
            "crs": crs,
            "f": output_format,
        }
        return await self._get(path, params=params)

    async def get_radius_raw(
        self,
        collection_id: str,
        coords: str,
        within: float,
        within_units: str = "km",
        instance_id: Optional[str] = None,
        parameter_names: Optional[str] = None,
        datetime_val: Optional[str] = None,
        crs: Optional[str] = None,
        output_format: str = "CoverageJSON",
    ) -> dict[str, Any]:
        """Low-level radius query returning raw CoverageJSON."""
        if instance_id:
            path = f"/collections/{collection_id}/instances/{instance_id}/radius"
        else:
            path = f"/collections/{collection_id}/radius"

        params = {
            "coords": coords,
            "within": within,
            "within-units": within_units,
            "parameter-name": parameter_names,
            "datetime": datetime_val,
            "crs": crs,
            "f": output_format,
        }
        return await self._get(path, params=params)

    async def get_area_raw(
        self,
        collection_id: str,
        coords: str,
        instance_id: Optional[str] = None,
        parameter_names: Optional[str] = None,
        datetime_val: Optional[str] = None,
        crs: Optional[str] = None,
        output_format: str = "CoverageJSON",
    ) -> dict[str, Any]:
        """Low-level area query returning raw CoverageJSON."""
        if instance_id:
            path = f"/collections/{collection_id}/instances/{instance_id}/area"
        else:
            path = f"/collections/{collection_id}/area"

        params = {
            "coords": coords,
            "parameter-name": parameter_names,
            "datetime": datetime_val,
            "crs": crs,
            "f": output_format,
        }
        return await self._get(path, params=params)

    async def get_cube_raw(
        self,
        collection_id: str,
        bbox: str,
        instance_id: Optional[str] = None,
        parameter_names: Optional[str] = None,
        datetime_val: Optional[str] = None,
        crs: Optional[str] = None,
        output_format: str = "CoverageJSON",
    ) -> dict[str, Any]:
        """Low-level bounding box cube query returning raw CoverageJSON."""
        if instance_id:
            path = f"/collections/{collection_id}/instances/{instance_id}/cube"
        else:
            path = f"/collections/{collection_id}/cube"

        params = {
            "bbox": bbox,
            "parameter-name": parameter_names,
            "datetime": datetime_val,
            "crs": crs,
            "f": output_format,
        }
        return await self._get(path, params=params)

    async def get_point_forecast(
        self,
        latitude: float,
        longitude: float,
        collection_id: str = DEFAULT_COLLECTION,
        instance_id: Optional[str] = None,
        parameters: Optional[list[str]] = None,
        datetime_range: Optional[str] = None,
    ) -> dict[str, Any]:
        """High-level helper to retrieve structured forecast series for a point (lat, lon)."""
        if not instance_id:
            instance_id = await self.get_latest_instance_id(collection_id)

        default_params = ["T_2M", "TOT_PREC", "U_10M", "V_10M", "CLCT", "PMSL", "WW"]
        param_list = parameters if parameters else default_params
        param_str = ",".join(param_list)

        coords_wkt = f"POINT({longitude} {latitude})"
        raw_data = await self.get_position_raw(
            collection_id=collection_id,
            coords=coords_wkt,
            instance_id=instance_id,
            parameter_names=param_str,
            datetime_val=datetime_range,
        )

        coverages = raw_data.get("coverages", [])
        if not coverages:
            return {
                "collection_id": collection_id,
                "instance_id": instance_id,
                "latitude": latitude,
                "longitude": longitude,
                "timestamps": [],
                "forecast": [],
                "raw_response": raw_data,
            }

        coverage = coverages[0]
        timestamps = coverage.get("domain", {}).get("axes", {}).get("t", {}).get("values", [])
        ranges = coverage.get("ranges", {})
        forecast_ref_time = coverage.get("cf:forecast_reference_time", instance_id)

        series: list[dict[str, Any]] = []
        for i, ts in enumerate(timestamps):
            point_data: dict[str, Any] = {"time": ts}
            for param in param_list:
                if param in ranges:
                    vals = ranges[param].get("values", [])
                    if i < len(vals):
                        val = vals[i]
                        # Convert Kelvin to Celsius if T_2M or TD_2M
                        if param in ("T_2M", "TD_2M") and val is not None:
                            point_data[f"{param}_celsius"] = round(val - 273.15, 2)
                        point_data[param] = val
            series.append(point_data)

        return {
            "collection_id": collection_id,
            "instance_id": instance_id,
            "forecast_reference_time": forecast_ref_time,
            "latitude": latitude,
            "longitude": longitude,
            "total_timesteps": len(timestamps),
            "forecast": series,
        }
