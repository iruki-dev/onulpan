"""중요도 점수 (4단계와 편집기가 공유).

importance = log2(1 + n_outlets) × (1 + 0.25 (n_groups − 1)) × e^(−Δt / 18h)

매체 수는 로그로 누르고(통신사 전재로 부풀려지는 것을 막는다), 서로 다른 매체군이 많을수록 가산한다.
매체의 정치 성향은 어디에도 쓰지 않는다. Δt는 묶음의 마지막 기사 이후 경과 시간이다.
"""
from __future__ import annotations

import math
from datetime import datetime


def importance(n_outlets: int, n_groups: int, last_seen: datetime, now: datetime,
               group_bonus: float = 0.25, decay_hours: float = 18.0) -> float:
    dt_h = max(0.0, (now - last_seen).total_seconds() / 3600.0)
    return (
        math.log2(1 + max(0, n_outlets))
        * (1 + group_bonus * (max(1, n_groups) - 1))
        * math.exp(-dt_h / decay_hours)
    )


def explain(n_outlets: int, n_groups: int, last_seen: datetime, now: datetime,
            group_bonus: float = 0.25, decay_hours: float = 18.0) -> dict:
    dt_h = max(0.0, (now - last_seen).total_seconds() / 3600.0)
    return {
        "n_outlets": n_outlets,
        "n_groups": n_groups,
        "hours_since_last": round(dt_h, 2),
        "outlet_term": round(math.log2(1 + max(0, n_outlets)), 4),
        "group_term": round(1 + group_bonus * (max(1, n_groups) - 1), 4),
        "decay_term": round(math.exp(-dt_h / decay_hours), 4),
        "score": round(importance(n_outlets, n_groups, last_seen, now, group_bonus, decay_hours), 4),
    }
