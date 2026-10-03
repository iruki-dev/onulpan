"""V1~V11. 규칙마다 파일 하나. 순서가 곧 실행 순서다."""
from . import (v01_schema, v02_sources, v03_numbers, v04_dates, v05_proper_nouns, v06_quotes, v07_copy,
               v08_banned, v09_conflicts, v10_fact_alignment, v11_semantic)

ALL = [v01_schema, v02_sources, v03_numbers, v04_dates, v05_proper_nouns, v06_quotes, v07_copy,
       v08_banned, v09_conflicts, v10_fact_alignment, v11_semantic]
