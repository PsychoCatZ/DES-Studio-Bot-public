from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DataValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Category:
    id: str
    title: str
    short_title: str
    active: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class Service:
    id: str
    category_id: str
    title: str
    short_description: str
    price_from: int | None
    price_to: int | None
    price_text: str
    active: bool
    sort_order: int
    full_description: str = ""
    features: tuple[str, ...] = ()
    portfolio_ids: tuple[str, ...] = ()

    @property
    def display_price(self) -> str:
        if self.price_text:
            return self.price_text
        if self.price_from is not None and self.price_to is not None:
            return f"{self.price_from:,}–{self.price_to:,} ₽".replace(",", " ")
        if self.price_from is not None:
            return f"от {self.price_from:,} ₽".replace(",", " ")
        return "После оценки технического задания"


@dataclass(frozen=True, slots=True)
class PortfolioProject:
    id: str
    title: str
    short_description: str
    image: str | None
    url: str | None
    active: bool
    sort_order: int


class Catalog:
    def __init__(self, categories: list[Category], services: list[Service]) -> None:
        self._categories = {item.id: item for item in categories}
        self._services = {item.id: item for item in services}

    @property
    def categories(self) -> list[Category]:
        return sorted(
            (item for item in self._categories.values() if item.active),
            key=lambda item: (item.sort_order, item.title),
        )

    @property
    def services(self) -> list[Service]:
        return sorted(
            (item for item in self._services.values() if item.active),
            key=lambda item: (item.sort_order, item.title),
        )

    def get_category(self, category_id: str) -> Category | None:
        item = self._categories.get(category_id)
        return item if item and item.active else None

    def get_service(self, service_id: str) -> Service | None:
        item = self._services.get(service_id)
        return item if item and item.active else None

    def services_for_category(self, category_id: str) -> list[Service]:
        return [item for item in self.services if item.category_id == category_id]


class Portfolio:
    def __init__(self, projects: list[PortfolioProject]) -> None:
        self._projects = {item.id: item for item in projects}

    @property
    def projects(self) -> list[PortfolioProject]:
        return sorted(
            (item for item in self._projects.values() if item.active),
            key=lambda item: (item.sort_order, item.title),
        )

    def get(self, project_id: str) -> PortfolioProject | None:
        item = self._projects.get(project_id)
        return item if item and item.active else None


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise DataValidationError(f"Data file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataValidationError(f"Invalid JSON in {path}: {exc}") from exc


def _require(record: dict[str, Any], fields: tuple[str, ...], context: str) -> None:
    missing = [field for field in fields if field not in record]
    if missing:
        raise DataValidationError(f"{context}: missing fields: {', '.join(missing)}")


def load_catalog(path: Path) -> Catalog:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise DataValidationError("catalog.json root must be an object")
    categories_raw = raw.get("categories")
    services_raw = raw.get("services")
    if not isinstance(categories_raw, list) or not isinstance(services_raw, list):
        raise DataValidationError("catalog.json must contain categories and services arrays")

    categories: list[Category] = []
    category_ids: set[str] = set()
    for index, item in enumerate(categories_raw):
        if not isinstance(item, dict):
            raise DataValidationError(f"category #{index + 1} must be an object")
        _require(item, ("id", "title", "short_title", "active", "sort_order"), f"category #{index + 1}")
        if item["id"] in category_ids:
            raise DataValidationError(f"duplicate category id: {item['id']}")
        category_ids.add(item["id"])
        categories.append(Category(**item))

    services: list[Service] = []
    service_ids: set[str] = set()
    required = (
        "id", "category_id", "title", "short_description", "price_from",
        "price_to", "price_text", "active", "sort_order",
    )
    for index, item in enumerate(services_raw):
        if not isinstance(item, dict):
            raise DataValidationError(f"service #{index + 1} must be an object")
        _require(item, required, f"service #{index + 1}")
        if item["id"] in service_ids:
            raise DataValidationError(f"duplicate service id: {item['id']}")
        if item["category_id"] not in category_ids:
            raise DataValidationError(
                f"service {item['id']} refers to unknown category {item['category_id']}"
            )
        service_ids.add(item["id"])
        normalized = dict(item)
        normalized["features"] = tuple(normalized.get("features", ()))
        normalized["portfolio_ids"] = tuple(normalized.get("portfolio_ids", ()))
        services.append(Service(**normalized))
    return Catalog(categories, services)


def load_portfolio(path: Path) -> Portfolio:
    raw = _read_json(path)
    if not isinstance(raw, list):
        raise DataValidationError("portfolio.json root must be an array")
    projects: list[PortfolioProject] = []
    project_ids: set[str] = set()
    required = ("id", "title", "short_description", "image", "url", "active", "sort_order")
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DataValidationError(f"portfolio project #{index + 1} must be an object")
        _require(item, required, f"portfolio project #{index + 1}")
        if item["id"] in project_ids:
            raise DataValidationError(f"duplicate portfolio id: {item['id']}")
        project_ids.add(item["id"])
        projects.append(PortfolioProject(**item))
    return Portfolio(projects)
