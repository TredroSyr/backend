"""Services package for products app."""

from __future__ import annotations

from .pricing import resolve_product_price

__all__ = ["resolve_product_price"]
