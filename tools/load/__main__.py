"""Нагрузочный прогон (фаза 7d, open-questions №62).

just load up          # отдельный стенд dutyflow-load на http://localhost:9080
just load populate    # 50 тыс. человек, 5 000 операторов, распределённый месяц (десятки минут)
just load run         # 300 операторов, 10 минут → docs/benchmarks/load.md
just load down        # удалить стенд вместе с данными
"""

import argparse
import io
import sys

from tools.load import populate, run, stand


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m tools.load", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("up", help="поднять отдельный стенд")
    sub.add_parser("down", help="удалить стенд и его данные")
    pop = sub.add_parser("populate", help="наполнить стенд")
    pop.add_argument("--people", type=int, default=50_000)
    pop.add_argument("--operators", type=int, default=5_000)
    pop.add_argument("--active", type=int, default=300)
    pop.add_argument("--resume", action="store_true", help="продолжить с графиков (шаги 4–5)")
    r = sub.add_parser("run", help="нагрузка и отчёт")
    r.add_argument("--users", type=int, default=300)
    r.add_argument("--duration", type=int, default=600, help="секунд замера")
    r.add_argument("--ramp", type=int, default=60, help="секунд разгона")
    r.add_argument("--think", type=float, default=10.0, help="средняя пауза между действиями, с")
    r.add_argument("--probe", type=int, default=30, help="период замера автораспределения, с")
    r.add_argument("--procs", type=int, default=6, help="процессов генератора нагрузки")
    r.add_argument("--name", default="load", help="docs/benchmarks/<name>.md и .json")
    args = parser.parse_args()
    if args.command == "up":
        stand.up()
    elif args.command == "down":
        stand.down()
    elif args.command == "populate":
        populate.main(args.people, args.operators, args.active, args.resume)
    else:
        run.main(
            args.users, args.duration, args.ramp, args.think, args.probe, args.procs, args.name
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
