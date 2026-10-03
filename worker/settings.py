"""설정: config/beta.yaml을 기본으로, 출시 모드는 config/launch.yaml로 덮어쓴다.

모드는 환경 변수 ONULPAN_MODE(beta|launch). 코드는 같고 설정값만 다르다.
"""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
RULES_DIR = ROOT / "rules"
PROMPTS_DIR = ROOT / "prompts"


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings(dict):
    """점(.) 경로로 꺼내 쓰는 설정 사전. s.get_path('cluster.join')"""

    def get_path(self, path: str, default: Any = None) -> Any:
        cur: Any = self
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def mode(self) -> str:
        return self["mode"]

    @property
    def database_url(self) -> str:
        return os.environ.get("DATABASE_URL", "postgresql://onulpan:onulpan@localhost:5432/onulpan")


def load_settings(mode: str | None = None, overrides: dict | None = None) -> Settings:
    mode = mode or os.environ.get("ONULPAN_MODE", "beta")
    if mode not in ("beta", "launch"):
        raise ValueError(f"unknown ONULPAN_MODE: {mode}")
    data = yaml.safe_load((CONFIG_DIR / "beta.yaml").read_text(encoding="utf-8"))
    if mode == "launch":
        data = _merge(data, yaml.safe_load((CONFIG_DIR / "launch.yaml").read_text(encoding="utf-8")))
    budget = os.environ.get("ONULPAN_BUDGET_USD")
    if budget:
        data["budget"]["monthly_usd"] = float(budget)
    if overrides:
        data = _merge(data, overrides)
    return Settings(data)


@lru_cache(maxsize=1)
def settings() -> Settings:
    return load_settings()
