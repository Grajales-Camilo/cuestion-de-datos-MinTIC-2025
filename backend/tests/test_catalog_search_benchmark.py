import pytest

from app.catalog.search_benchmark import (
    build_representative_queries,
    compute_latency_percentiles,
    percentile,
)


def test_percentile_of_single_value() -> None:
    assert percentile([42.0], 95) == 42.0


def test_percentile_empty_is_zero() -> None:
    assert percentile([], 95) == 0.0


def test_percentile_p50_of_sorted_range() -> None:
    values = [float(i) for i in range(1, 101)]  # 1..100
    assert percentile(values, 50) == pytest.approx(50.5, abs=0.5)
    assert percentile(values, 99) == pytest.approx(99.0, abs=1.0)


def test_compute_latency_percentiles_keys() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = compute_latency_percentiles(values)
    assert set(result.keys()) == {"p50", "p95", "p99"}
    assert result["p50"] <= result["p95"] <= result["p99"]


def test_build_representative_queries_meets_minimum() -> None:
    categories = [f"categoria {i}" for i in range(30)]
    places = ["Antioquia", "Boyacá", "Santander"]

    queries = build_representative_queries(categories, places, minimum=100)

    assert len(queries) >= 100
    assert len(queries) == len(set(queries))  # sin duplicados


def test_build_representative_queries_uses_real_topics_verbatim() -> None:
    categories = ["Educación"] + [f"categoria {i}" for i in range(29)]
    places = ["Antioquia"]

    queries = build_representative_queries(categories, places, minimum=100)

    assert any("educación" in q for q in queries)
    assert any("antioquia" in q.lower() for q in queries)


def test_build_representative_queries_raises_when_insufficient() -> None:
    with pytest.raises(ValueError, match="se requieren"):
        build_representative_queries(["unica categoria"], [], minimum=100)


def test_build_representative_queries_is_deterministic() -> None:
    categories = [f"categoria {i}" for i in range(30)]
    places = ["Antioquia", "Boyacá"]

    first = build_representative_queries(categories, places, minimum=100)
    second = build_representative_queries(categories, places, minimum=100)

    assert first == second
