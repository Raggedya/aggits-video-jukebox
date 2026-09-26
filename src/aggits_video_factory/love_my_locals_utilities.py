from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


UTILITY_TYPES = ("eat", "stay", "whats-on", "house-prices")
UTILITY_FIXTURE_SOURCE = "development-fixture"
UTILITY_FIXTURE_NOTICE = "TEST DATA • DEVELOPMENT FIXTURE • NOT PRODUCTION DATA"


def _fixture_items(prefix: str, category: str, descriptions: Iterable[str]) -> list[dict[str, Any]]:
    """Return nine deliberately unmistakable local development fixtures."""
    items: list[dict[str, Any]] = []
    values = list(descriptions)
    for index in range(9):
        items.append({
            "id": f"{prefix}-fixture-{index + 1:02d}",
            "name": f"{prefix.upper()} TEST FIXTURE {index + 1:02d}",
            "category": category,
            "locality": "TEST LOCALITY",
            "description": values[index % len(values)],
            "fixture": True,
        })
    return items


_BASE_FIXTURES: dict[str, dict[str, Any]] = {
    "eat": {
        "utilityType": "eat",
        "title": "EAT",
        "icon": "🍴",
        "headline": "GREAT FOOD AROUND {location}",
        "kicker": "CAFÉS • RESTAURANTS • PUBS • LOCAL FAVOURITES",
        "summary": "A development-only preview of the places-to-eat information chamber.",
        "items": _fixture_items("eat", "TEST VENUE • DEVELOPMENT ONLY", (
            "Placeholder café information for utility layout testing.",
            "Placeholder restaurant information for utility layout testing.",
            "Placeholder pub information for utility layout testing.",
        )),
    },
    "stay": {
        "utilityType": "stay",
        "title": "STAY",
        "icon": "🛏",
        "headline": "PLACES TO STAY AROUND {location}",
        "kicker": "HOTELS • MOTELS • CABINS • LOCAL STAYS",
        "summary": "A development-only preview of the accommodation information chamber.",
        "items": _fixture_items("stay", "TEST ACCOMMODATION • DEVELOPMENT ONLY", (
            "Placeholder hotel information. No live price or availability data.",
            "Placeholder motel information. No live price or availability data.",
            "Placeholder local-stay information. No live price or availability data.",
        )),
    },
    "whats-on": {
        "utilityType": "whats-on",
        "title": "WHAT’S ON",
        "icon": "★",
        "headline": "WHAT’S ON AROUND {location}",
        "kicker": "EVENTS • MUSIC • COMMUNITY • LOCAL HAPPENINGS",
        "summary": "A development-only preview of the local-events information chamber.",
        "items": [
            {
                "id": f"whats-on-fixture-{index + 1:02d}",
                "name": f"EVENT TEST FIXTURE {index + 1:02d}",
                "category": "TEST EVENT • DEVELOPMENT ONLY",
                "locality": "TEST VENUE",
                "date": "TEST DATE",
                "time": "TEST TIME",
                "description": "Placeholder event information for utility layout testing.",
                "fixture": True,
            }
            for index in range(9)
        ],
    },
    "house-prices": {
        "utilityType": "house-prices",
        "title": "HOUSE PRICES",
        "icon": "⌂",
        "headline": "HOUSE PRICES AROUND {location}",
        "kicker": "MARKET SNAPSHOT • INFORMATION ONLY",
        "summary": "A development-only preview. No verified market or property data is connected.",
        "market": {
            "medianHousePrice": "TEST DATA",
            "medianUnitPrice": "TEST DATA",
            "twelveMonthMovement": "TEST DATA",
        },
        "items": [
            {
                "id": f"house-prices-fixture-{index + 1:02d}",
                "name": f"PROPERTY TEST FIXTURE {index + 1:02d}",
                "category": "TEST PROPERTY • DEVELOPMENT ONLY",
                "locality": "TEST LOCALITY",
                "price": "TEST DATA",
                "bedrooms": "TEST",
                "bathrooms": "TEST",
                "carSpaces": "TEST",
                "description": "Placeholder property example for utility layout testing.",
                "fixture": True,
            }
            for index in range(9)
        ],
    },
}


def build_development_utility_fixtures(
    locations: Iterable[str],
    resolved_geography: str,
    *,
    include_eat: bool = True,
) -> dict[str, dict[str, Any]]:
    """Normalised fixture-provider output for the Love My Locals utility service.

    This is intentionally not a live-data provider. Future authorised provider
    adapters can emit this same schema without changing the utility UI.
    """
    location_names = [str(value).strip() for value in locations if str(value).strip()]
    location_name = location_names[0] if location_names else "TEST LOCATION"
    geography_parts = [part.strip() for part in str(resolved_geography or "").split(",") if part.strip()]
    state = geography_parts[0] if geography_parts else "TEST REGION"
    country = geography_parts[-1] if len(geography_parts) > 1 else "TEST COUNTRY"
    location = {"name": location_name, "state": state, "country": country}
    bundle = deepcopy(_BASE_FIXTURES)
    if not include_eat:
        bundle.pop("eat", None)
    for utility_type, data in bundle.items():
        data.update({
            "schemaVersion": 1,
            "source": UTILITY_FIXTURE_SOURCE,
            "environment": "development",
            "notice": UTILITY_FIXTURE_NOTICE,
            "generatedAt": "DEVELOPMENT FIXTURE — NOT LIVE DATA",
            "location": dict(location),
            "headline": str(data["headline"]).format(location=location_name.upper()),
        })
        data["items"] = list(data.get("items", []))[:9]
        if utility_type not in UTILITY_TYPES:
            raise ValueError(f"Unsupported Love My Locals utility fixture: {utility_type}")
    return bundle


def fixture_provider_metadata(*, live_eat: bool = False, eat_endpoint: str = "", project_slug: str = "") -> dict[str, Any]:
    return {
        "provider": "google-places-new" if live_eat else UTILITY_FIXTURE_SOURCE,
        "environment": "production" if live_eat else "development",
        "notice": "" if live_eat else UTILITY_FIXTURE_NOTICE,
        "liveDataConnected": live_eat,
        "eat": {
            "provider": "google-places-new" if live_eat else UTILITY_FIXTURE_SOURCE,
            "mode": "live" if live_eat else "development-fixture",
            "endpoint": eat_endpoint if live_eat else "",
            "projectSlug": project_slug if live_eat else "",
            "attribution": "Google Maps" if live_eat else "",
            "photosEnabled": False,
            "cacheStrategy": "page-session-only" if live_eat else "fixture",
        },
        "maxItemsPerUtility": 9,
        "itemsPerPage": 3,
    }
