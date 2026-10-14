def slugify_keyword(keyword: str) -> str:
    return keyword.strip().lower().replace(" ", "_").replace("/", "_")
