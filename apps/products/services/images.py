"""The cover image a product shows, wherever it is rendered.

The product endpoints and every document line draw the same thumbnail, so both
the prefetch and the "which row is the cover" rule live here once. Reading the
image off each product instead would cost a query per row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch

from apps.products.models import ProductImage

if TYPE_CHECKING:
    from apps.products.models import Product

#: Attribute `primary_image_prefetch` writes and `primary_image` reads back.
PRIMARY_IMAGES_ATTR = "primary_images"


def primary_image_prefetch(path: str = "images") -> Prefetch:
    """Prefetch only the cover images.

    `path` is how products are reached from the queryset being prefetched:
    `"images"` from `Product` itself, `"product__images"` from a document line.
    """
    return Prefetch(
        path,
        queryset=ProductImage.objects.filter(is_primary=True),
        to_attr=PRIMARY_IMAGES_ATTR,
    )


def primary_image(product: Product) -> ProductImage | None:
    """The product's cover image, from whichever prefetch the caller arranged."""
    prefetched = getattr(product, PRIMARY_IMAGES_ATTR, None)
    if prefetched is not None:
        return prefetched[0] if prefetched else None

    if "images" in getattr(product, "_prefetched_objects_cache", {}):
        return next((image for image in product.images.all() if image.is_primary), None)

    return product.images.filter(is_primary=True).first()


def primary_image_payload(product: Product, request=None) -> dict | None:
    """`{id, image, alt_text}` for the cover image, or None when there is none.

    `image` is absolute whenever a request is at hand, matching what DRF renders
    for a `FileField`, so no client has to know the media host.
    """
    image = primary_image(product)
    if image is None or not image.image:
        return None

    url = image.image.url
    return {
        "id": image.id,
        "image": request.build_absolute_uri(url) if request is not None else url,
        "alt_text": image.alt_text,
    }
