"""UUIDv7 (RFC 9562) — идентификаторы всех сущностей, ADR-0011.

В Python 3.12 нет `uuid.uuid7`, поэтому реализация своя: 48 бит миллисекунд Unix-времени,
затем 74 случайных бита. Монотонность внутри одной миллисекунды не гарантируется —
для B-tree достаточно упорядоченности по времени.
"""

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 бит, лишнее отрежем масками
    rand_a = rand >> 68 & 0xFFF  # 12 бит
    rand_b = rand & 0x3FFF_FFFF_FFFF_FFFF  # 62 бита
    value = (unix_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76  # версия
    value |= rand_a << 64
    value |= 0b10 << 62  # вариант RFC 4122/9562
    value |= rand_b
    return uuid.UUID(int=value)


# Пространство имён детерминированных идентификаторов категорий личного состава (ADR-0018):
# миграции personnel и scheduling получают одинаковые id по названию категории, не обращаясь
# к чужой БД. Значение зашито и в сами миграции — менять нельзя.
CATEGORY_NAMESPACE = uuid.UUID("5f0c1d7e-3b1a-4c1e-9a58-0d7f6f1e2a18")


def category_id(name: str) -> uuid.UUID:
    """Id базовой категории по её названию («Курсант», «Постоянный состав»…)."""
    return uuid.uuid5(CATEGORY_NAMESPACE, name)
