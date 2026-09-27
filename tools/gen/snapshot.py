"""Синтетический снимок задачи (ADR-0013) в файл — для отладки движка и экспериментов.

uv run python tools/gen/snapshot.py --people 5000 --seed 7 > snapshot.json
"""

import argparse
import sys

from pydantic_core import to_json

from allocation.synthetic import generate_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", type=int, default=300)
    parser.add_argument("--children", type=int, default=4)
    parser.add_argument("--duty-types", type=int, default=6)
    parser.add_argument("--clearance-share", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    snapshot = generate_snapshot(
        people=args.people,
        children=args.children,
        duty_types=args.duty_types,
        clearance_share=args.clearance_share,
        seed=args.seed,
    )
    sys.stdout.buffer.write(to_json(snapshot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
