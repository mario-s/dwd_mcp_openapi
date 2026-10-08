import pytest
from dwd_client import DwdEdrClient, DEFAULT_COLLECTION
from main import server, get_point_weather_forecast, list_model_collections
import json


@pytest.mark.asyncio
async def test_client_list_collections(httpx_mock):
    httpx_mock.add_response(
        url="https://nwp.opendata-api.dwd.de/v1beta1/collections",
        json={"collections": [{"id": "ICON-D2-RUC@single_level", "title": "ICON D2 RUC"}]},
    )
    client = DwdEdrClient()
    collections = await client.list_collections()
    assert len(collections) == 1
    assert collections[0]["id"] == "ICON-D2-RUC@single_level"


@pytest.mark.asyncio
async def test_client_get_point_forecast(httpx_mock):
    httpx_mock.add_response(
        url=f"https://nwp.opendata-api.dwd.de/v1beta1/collections/{DEFAULT_COLLECTION}/instances",
        json={"instances": [{"id": "2026-09-24T08:00:00Z"}]},
    )
    httpx_mock.add_response(
        url=(
            f"https://nwp.opendata-api.dwd.de/v1beta1/collections/{DEFAULT_COLLECTION}/"
            "instances/2026-09-24T08:00:00Z/position"
            "?coords=POINT%2813.405+52.52%29&parameter-name=T_2M%2CTOT_PREC%2CU_10M%2CV_10M%2CCLCT%2CPMSL%2CWW&f=CoverageJSON"
        ),
        json={
            "coverages": [
                {
                    "domain": {"axes": {"t": {"values": ["2026-09-24T08:00:00Z"]}}},
                    "ranges": {"T_2M": {"values": [286.15]}},
                    "cf:forecast_reference_time": "2026-09-24T08:00:00Z",
                }
            ]
        },
    )

    client = DwdEdrClient()
    result = await client.get_point_forecast(latitude=52.52, longitude=13.405)
    assert result["latitude"] == 52.52
    assert result["longitude"] == 13.405
    assert result["total_timesteps"] == 1
    assert result["forecast"][0]["T_2M_celsius"] == 13.0


@pytest.mark.asyncio
async def test_mcp_tool_list_collections(httpx_mock):
    httpx_mock.add_response(
        url="https://nwp.opendata-api.dwd.de/v1beta1/collections",
        json={"collections": [{"id": "ICON-D2-RUC@single_level"}]},
    )
    res_str = await list_model_collections()
    data = json.loads(res_str)
    assert len(data) == 1
    assert data[0]["id"] == "ICON-D2-RUC@single_level"
