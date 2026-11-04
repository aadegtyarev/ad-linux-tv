"""Fixed Browser-tile search destinations; never an arbitrary navigation API."""

SEARCH_URLS = {
    "yandex": "https://ya.ru/",
    "google": "https://www.google.com/",
    "duckduckgo": "https://duckduckgo.com/",
}


def validate_search_provider(value):
    if not isinstance(value, str) or value not in SEARCH_URLS:
        raise ValueError("invalid browser search provider")
    return value


def browser_tile(config):
    return next((item for item in config["services"] if item["id"] == "browser"), None)


def search_state(config):
    tile = browser_tile(config)
    return {
        "browser_search_available": tile is not None,
        "browser_search": config.get("browser_search"),
        "browser_search_custom": tile is not None and tile["url"] != SEARCH_URLS["yandex"],
    }
