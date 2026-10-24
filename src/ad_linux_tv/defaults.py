"""Initial supported streaming services."""

from copy import deepcopy

DEFAULT_SERVICES = [
    {"id": "vk", "name": "VK Видео", "url": "https://vk.com/video", "color": "#0077FF"},
    {"id": "kinopoisk", "name": "КиноПоиск", "url": "https://hd.kinopoisk.ru/", "color": "#FF6600"},
    {"id": "music", "name": "Яндекс Музыка", "url": "https://music.yandex.ru/", "color": "#FFCC00"},
    {"id": "youtube", "name": "YouTube", "url": "https://www.youtube.com/", "color": "#FF0000"},
    {"id": "browser", "name": "Браузер", "url": "https://ya.ru/", "color": "#6B7280"},
]


def default_services():
    return deepcopy(DEFAULT_SERVICES)
