"""Shared dictionary contracts for the phase-2 demo core.

Dataset loaders return a snapshot with ``catalog``, ``vendors``, ``raw_offers``,
``offers`` (normalized, including rejected records), and ``id``/``kind``.

``evaluate(snapshot, rfq)`` takes an RFQ with ``lines``. Each line has ``id``,
``catalog_item_id`` and positive integer ``qty_base``. RFQ options are
``preference`` (lowest_cost or fastest_delivery), optional ``budget_irr`` and
``max_lead_days``, and ``requires_declared_invoice`` (bool).

All money is integer IRR. Unknown values are represented by ``None``, never 0.
"""

from typing import Literal, TypedDict


InvoiceStatus = Literal[
    "unknown", "declared_yes", "declared_no", "verified_yes", "verified_no"
]
Preference = Literal["lowest_cost", "fastest_delivery"]


class CatalogItem(TypedDict):
    id: str
    category: str
    category_path: list[str]
    name: str
    aliases: list[str]
    base_unit: str


class Vendor(TypedDict):
    id: str
    name: str
    shipping_irr: int | None
    minimum_order_irr: int | None
    synthetic: bool


class NormalizedOffer(TypedDict):
    id: str
    raw_record_id: str
    vendor_id: str
    catalog_item_id: str | None
    package_size_base: int | None
    package_price_irr: int | None
    min_packages: int | None
    package_step: int | None
    stock_packages: int | None
    lead_days: int | None
    invoice_status: InvoiceStatus
    tax_status: str
    normalization_status: str
    rejection_reason: str | None
    normalization_steps: list[str]


class RFQLine(TypedDict):
    id: str
    catalog_item_id: str
    qty_base: int


class RFQ(TypedDict):
    lines: list[RFQLine]
    preference: Preference
    budget_irr: int | None
    max_lead_days: int | None
    requires_declared_invoice: bool
