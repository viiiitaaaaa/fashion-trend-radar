import re


def _parse_price(price_str):
    if not isinstance(price_str, str):
        return None
    m = re.search(r"([\d.]+)", price_str.replace(",", ""))
    return float(m.group(1)) if m else None


def _parse_orders(orders_str):
    if not isinstance(orders_str, str):
        return 0
    m = re.search(r"([\d,]+)", orders_str)
    return int(m.group(1).replace(",", "")) if m else 0


def passes_quality_gate(product, min_rating=4.0, min_price=15.0, max_price=60.0, min_orders=0):
    """Only products worth sourcing: rated above min_rating, priced in
    [min_price, max_price], with sales above min_orders."""
    rating = product.get("rating")
    try:
        rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating = None

    price = _parse_price(product.get("price"))
    orders = _parse_orders(product.get("orders"))

    if rating is None or rating <= min_rating:
        return False
    if price is None or price < min_price or price > max_price:
        return False
    if orders <= min_orders:
        return False
    return True


def filter_products(products, min_rating=4.0, min_price=15.0, max_price=60.0, min_orders=0):
    return [p for p in products if passes_quality_gate(p, min_rating, min_price, max_price, min_orders)]
