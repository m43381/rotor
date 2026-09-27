"""Конфигурация прогона: веса скоринга и параметры вне кода (ADR-0006, «Последствия»).

Значения по умолчанию лежат в `allocation/config/default.yaml`; прогон может переопределить
любое поле. Числа по умолчанию — утверждённые ответы open-questions №42–43; точные значения
подбираются в экспериментах фазы 5.
"""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "config" / "default.yaml"


class PeopleWeights(BaseModel):
    """Веса признаков кандидата-человека (уровень 3): стоимость = Σ вес × признак."""

    load: float = 1.0  # нагрузка с затуханием, нарядо-сутки × вес наряда
    same_type: float = 0.5  # то же, только по этому типу наряда
    holiday: float = 1.0  # праздничные наряды — учитываются, если ячейка в выходной
    recency: float = 2.0  # близость к другому наряду человека (отдых «впритык»)


class UnitWeights(BaseModel):
    """Веса признаков подразделения-исполнителя (распределение по подразделениям)."""

    quota: float = 1.0  # насколько подразделение уже выбрало свою квоту
    same_day: float = 0.5  # сколько ролей уже отдано ему в этот день
    capacity: float = 0.3  # запас людей (больше — дешевле)
    debt_lambda: float = 0.5  # поправка квоты на прошлую нагрузку (долг), 0 — без поправки


class EngineConfig(BaseModel):
    kind: Literal["people", "units"] = "people"
    # fill — только пустые места; rebuild — можно заменить свои незакреплённые назначения (№41)
    mode: Literal["fill", "rebuild"] = "fill"
    # Область прогона: id ячеек снимка; None — весь месяц графика
    cell_ids: list[str] | None = None
    half_life_days: float = Field(default=30.0, gt=0)  # затухание нагрузки (№42)
    holiday_weight: float = Field(default=1.5, ge=1)  # вес наряда в выходной (№43)
    people_weights: PeopleWeights = Field(default_factory=PeopleWeights)
    unit_weights: UnitWeights = Field(default_factory=UnitWeights)
    # Распределение по подразделениям: может ли подразделение графика оставить роль себе
    include_self: bool = False
    # Строгая проверка выполнимости максимальным потоком (уровень 2); на очень больших
    # задачах её можно выключить — граница тогда не считается
    strict_feasibility: bool = True
    strict_feasibility_max_edges: int = 5_000_000
    alternatives: int = Field(default=5, ge=0, le=20)

    # --- уровень 4 (фаза 5): метод и его пределы -------------------------------------------
    # auto — по размеру задачи (open-questions №46); остальные — принудительно
    method: Literal["auto", "greedy", "hungarian", "local_search", "cpsat"] = "auto"
    # Пороги auto по числу допустимых пар «человек × место» (эксперимент E4)
    auto_cpsat_max_pairs: int = 10_000
    auto_local_search_max_pairs: int = 2_000_000
    ls_iterations: int = Field(default=50_000, ge=0)
    ls_temperature: float = Field(default=0.5, ge=0)
    # CP-SAT: детерминированное время (одинаковый результат) и настенный предел (страховка,
    # open-questions №47); число потоков решателя
    cpsat_deterministic_time: float = Field(default=20.0, gt=0)
    cpsat_time_limit_s: float = Field(default=10.0, gt=0)
    cpsat_workers: int = Field(default=1, ge=1, le=32)
    # Стартовое решение и подсказка CP-SAT
    cpsat_hint: Literal["local_search", "greedy"] = "local_search"
    # Сужение модели: столько лучших кандидатов на место (0 — все допустимые)
    cpsat_candidates_per_place: int = Field(default=20, ge=0)
    # Скользящий горизонт: больше стольких пар — месяц решается окнами по window_days дней
    cpsat_window_pairs: int = 30_000
    window_days: int = Field(default=7, ge=0)

    # --- распределение по подразделениям ---------------------------------------------------
    apportionment: Literal["sainte_lague", "hamilton"] = "sainte_lague"
    units_method: Literal["auto", "greedy", "flow"] = "auto"


def load_defaults(path: Path = DEFAULT_FILE) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: ожидается словарь настроек")
    return data


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def make_config(
    override: dict[str, Any] | None = None, defaults: dict[str, Any] | None = None
) -> EngineConfig:
    """Настройки файла по умолчанию, поверх — настройки прогона."""
    base = load_defaults() if defaults is None else defaults
    return EngineConfig.model_validate(_merge(base, override or {}))
