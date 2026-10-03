import pytest

from worker.verify.numbers import extract_dates, extract_numbers, parse_korean_number


@pytest.mark.parametrize("raw,value", [
    ("1만2천", 12000), ("12,000", 12000), ("3.5", 3.5), ("1조 2000억", 1.2e12), ("2천", 2000), ("680조", 6.8e14),
])
def test_parse(raw, value):
    assert parse_korean_number(raw) == value


def test_units_normalized():
    a = {(n.value, n.unit) for n in extract_numbers("수출이 3.5% 늘었다")}
    b = {(n.value, n.unit) for n in extract_numbers("수출이 3.5퍼센트 늘었다")}
    assert a == b == {(3.5, "%")}


def test_same_value_different_spelling():
    a = {(n.value, n.unit) for n in extract_numbers("1만2천 명")}
    b = {(n.value, n.unit) for n in extract_numbers("12,000명")}
    assert a == b


def test_names_with_digits_are_not_numbers():
    assert extract_numbers("코로나19와 G20") == []


def test_native_numerals():
    assert [(n.value, n.unit) for n in extract_numbers("세 명이 다쳤다")] == [(3.0, "명")]


def test_dates():
    ds = extract_dates("2026년 10월 12일 발표했고 13일 다시 만났다")
    assert (2026, 10, 12) in {(d.year, d.month, d.day) for d in ds}
    assert any(d.day == 13 and d.month is None for d in ds)


def test_context_word():
    n = extract_numbers("사망자는 12명으로 늘었다", with_context=True)[0]
    assert n.context == "사망자"
