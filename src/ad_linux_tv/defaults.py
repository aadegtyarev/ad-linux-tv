"""Initial supported streaming services."""

from copy import deepcopy

DEFAULT_SERVICES = [
    {"id": "vk", "name": "VK Видео", "url": "https://vk.com/video"},
    {"id": "kinopoisk", "name": "КиноПоиск", "url": "https://hd.kinopoisk.ru/"},
    {"id": "music", "name": "Яндекс Музыка", "url": "https://music.yandex.ru/"},
    {"id": "youtube", "name": "YouTube", "url": "https://www.youtube.com/"},
    {"id": "browser", "name": "Браузер", "url": "https://ya.ru/"},
]


def default_services():
    return deepcopy(DEFAULT_SERVICES)
