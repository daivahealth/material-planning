"""
Tests for formula validation.
"""
import pytest
from app.services.formula import validate_formula, evaluate_formula


def test_valid_standard_expression():
    ok, err = validate_formula("(avg_daily * indent_days * (1 + safety_pct)) - closing_stock")
    assert ok is True
    assert err == ""


def test_valid_custom_expression():
    ok, err = validate_formula("avg_daily * indent_days * 2")
    assert ok is True


def test_invalid_syntax():
    ok, err = validate_formula("avg_daily * * indent_days")
    assert ok is False
    assert err != ""


def test_unknown_variable():
    ok, err = validate_formula("unknown_var * 10")
    assert ok is False


def test_non_numeric_result():
    ok, err = validate_formula("'hello'")
    assert ok is False


def test_evaluate_formula_correct():
    result = evaluate_formula("avg_daily * indent_days * 2", 10.0, 30, 0.0, 0.1)
    assert result == pytest.approx(600.0)


def test_evaluate_with_all_vars():
    result = evaluate_formula(
        "(avg_daily * indent_days * (1 + safety_pct)) - closing_stock",
        avg_daily=10.0, indent_days=30, closing_stock=50.0, safety_pct=0.10,
    )
    # (10 * 30 * 1.1) - 50 = 330 - 50 = 280
    assert result == pytest.approx(280.0)
