"""
Formula validation helper.
Uses simpleeval for safe expression evaluation — no arbitrary code execution.
"""
from simpleeval import EvalWithCompoundTypes, InvalidExpression
from typing import Tuple

DUMMY_VARS = {
    "avg_daily": 10.0,
    "indent_days": 30,
    "closing_stock": 50.0,
    "safety_pct": 0.10,
    "open_indent_qty": 0.0,
    "lead_time_days": 7,
    "safety_days": 3.0,
    "target_stock": 400.0,
}

STANDARD_FORMULA = (
    "avg_daily * (indent_days + safety_pct * indent_days + lead_time_days)"
    " - (closing_stock + open_indent_qty)"
)


def validate_formula(expr: str) -> Tuple[bool, str]:
    """
    Dry-run evaluate expr with dummy values.
    Returns (True, "") on success or (False, error_message) on failure.
    """
    try:
        evaluator = EvalWithCompoundTypes(names=DUMMY_VARS)
        result = evaluator.eval(expr)
        if not isinstance(result, (int, float)):
            return False, f"Expression must return a number, got {type(result).__name__}"
        return True, ""
    except InvalidExpression as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def evaluate_formula(expr: str, avg_daily: float, indent_days: int,
                     closing_stock: float, safety_pct: float,
                     open_indent_qty: float = 0.0,
                     lead_time_days: int = 0,
                     safety_days: float = 0.0,
                     target_stock: float = 0.0) -> float:
    evaluator = EvalWithCompoundTypes(names={
        "avg_daily": avg_daily,
        "indent_days": indent_days,
        "closing_stock": closing_stock,
        "safety_pct": safety_pct,
        "open_indent_qty": open_indent_qty,
        "lead_time_days": lead_time_days,
        "safety_days": safety_days,
        "target_stock": target_stock,
    })
    result = evaluator.eval(expr)
    return float(result)
