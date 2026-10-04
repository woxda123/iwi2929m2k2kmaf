import json
from pathlib import Path

_PATH = Path(__file__).with_name("ru.json")

with open(_PATH, encoding="utf-8") as _f:
    _TEXTS = json.load(_f)


def t(key: str, **kwargs) -> str:
    """Возвращает текст по ключу из ru.json и подставляет параметры."""
    text = _TEXTS[key]
    return text.format(**kwargs) if kwargs else text
