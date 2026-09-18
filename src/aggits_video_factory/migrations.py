from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5


LEGACY_PROJECT_SCHEMA_VERSION = 2
CURRENT_PROJECT_SCHEMA_VERSION = 3
SUPPORTED_PROJECT_SCHEMA_VERSIONS = frozenset({LEGACY_PROJECT_SCHEMA_VERSION, CURRENT_PROJECT_SCHEMA_VERSION})

# A fixed application namespace makes a legacy project's first in-memory ID
# deterministic. The generated UUID is persisted the first time that project is
# deliberately saved, after its original JSON has been backed up.
LEGACY_PROJECT_ID_NAMESPACE = UUID("c0f5d135-7622-4e96-87a5-66439cb896eb")


class ProjectMigrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectMigration:
    data: dict[str, Any]
    source_version: int
    target_version: int
    migrated: bool


def _schema_version(value: dict[str, Any]) -> int:
    raw = value.get("schemaVersion", LEGACY_PROJECT_SCHEMA_VERSION)
    if isinstance(raw, bool):
        raise ProjectMigrationError("Project schemaVersion must be an integer.")
    try:
        version = int(raw)
    except (TypeError, ValueError) as error:
        raise ProjectMigrationError("Project schemaVersion must be an integer.") from error
    if version not in SUPPORTED_PROJECT_SCHEMA_VERSIONS:
        raise ProjectMigrationError(f"Unsupported project schema version: {version}.")
    return version


def _legacy_project_id(value: dict[str, Any]) -> str:
    slug = str(value.get("slug") or "").strip().lower()
    created_at = str(value.get("created_at") or value.get("createdAt") or "").strip()
    title = str(value.get("title") or "").strip()
    identity_seed = "\0".join((slug, created_at, title))
    return str(uuid5(LEGACY_PROJECT_ID_NAMESPACE, identity_seed))


def migrate_project_dict(value: dict[str, Any]) -> ProjectMigration:
    """Return a validated current-schema copy without modifying the source mapping."""
    if not isinstance(value, dict):
        raise ProjectMigrationError("Project data must be a JSON object.")
    source_version = _schema_version(value)
    migrated = deepcopy(value)

    if source_version == LEGACY_PROJECT_SCHEMA_VERSION:
        legacy_business = migrated.get("business_config", migrated.get("businessConfig"))
        business_config = dict(legacy_business) if isinstance(legacy_business, dict) else {}
        explicit_shop_url = migrated.get("shop_url", migrated.get("shopUrl"))
        if "shop_url" not in business_config and "shopUrl" not in business_config:
            business_config["shop_url"] = explicit_shop_url or None
        migrated["id"] = str(migrated.get("id") or _legacy_project_id(migrated))
        migrated["project_type"] = "business"
        migrated["additional_urls"] = list(migrated.get("additional_urls", migrated.get("additionalUrls", [])) or [])
        migrated["business_config"] = business_config
        migrated["music_config"] = None
        migrated["schemaVersion"] = CURRENT_PROJECT_SCHEMA_VERSION

    return ProjectMigration(
        data=migrated,
        source_version=source_version,
        target_version=CURRENT_PROJECT_SCHEMA_VERSION,
        migrated=source_version != CURRENT_PROJECT_SCHEMA_VERSION,
    )
