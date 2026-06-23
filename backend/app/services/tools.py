"""Tool / function-calling framework (P37).

A small, registry-driven layer of safe, deterministic tools the model can call:
calculator, unit conversion, date/time, and campus info. Tools are pure Python
(no network, no I/O) so they're cheap, testable, and can't be abused.

The registry exposes:
  * ``SPECS`` — OpenAI/LiteLLM-style ``tools`` JSON schema for function calling.
  * ``run(name, args)`` — dispatch a validated call and return a string result.

The chat layer routes tool-eligible turns through the ``tool_use`` model
category (see models.json) and feeds results back for a grounded final answer.
"""
from __future__ import annotations

import ast
import datetime as _dt
import operator as _op
from typing import Any, Callable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# --- safe arithmetic evaluator (no eval) ------------------------------------
_BINOPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
    ast.Div: _op.truediv, ast.Pow: _op.pow, ast.Mod: _op.mod,
    ast.FloorDiv: _op.floordiv,
}
_UNARYOPS = {ast.UAdd: _op.pos, ast.USub: _op.neg}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression")


def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression (+ - * / // % **)."""
    try:
        tree = ast.parse(expression, mode="eval")
        val = _safe_eval(tree.body)
        return f"{expression} = {val:g}"
    except Exception:
        return "Could not evaluate that expression. Use numbers and + - * / // % ** only."


# --- unit conversion (a curated, common set) --------------------------------
_LINEAR = {  # to a base unit
    # length → meters
    ("km", "m"): 1000, ("m", "cm"): 100, ("m", "mm"): 1000, ("mi", "km"): 1.609344,
    ("ft", "m"): 0.3048, ("in", "cm"): 2.54,
    # mass → grams
    ("kg", "g"): 1000, ("lb", "kg"): 0.45359237,
    # data
    ("gb", "mb"): 1024, ("mb", "kb"): 1024,
}


def convert(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units (length, mass, temperature, data)."""
    f, t = from_unit.lower(), to_unit.lower()
    # temperature special cases
    if {f, t} <= {"c", "f", "k"}:
        c = value if f == "c" else (value - 32) * 5 / 9 if f == "f" else value - 273.15
        out = c if t == "c" else c * 9 / 5 + 32 if t == "f" else c + 273.15
        return f"{value}°{from_unit.upper()} = {round(out, 2)}°{to_unit.upper()}"
    if (f, t) in _LINEAR:
        return f"{value} {f} = {round(value * _LINEAR[(f, t)], 4)} {t}"
    if (t, f) in _LINEAR:
        return f"{value} {f} = {round(value / _LINEAR[(t, f)], 4)} {t}"
    return f"No known conversion from {from_unit} to {to_unit}."


def current_datetime(timezone: str = "IST") -> str:
    """Current date and time (defaults to IST, the campus timezone)."""
    now = _dt.datetime.now(IST)
    return now.strftime("%A, %d %B %Y, %H:%M IST")


_CAMPUS = {
    "name": "KSRM College of Engineering (KSRMCE)",
    "location": "Kadapa, Andhra Pradesh, India",
    "email_domain": "ksrmce.ac.in",
    "support": "Contact your department admin in the K-GPT admin console.",
}


def campus_info(topic: str = "general") -> str:
    """Return basic, non-sensitive campus information."""
    t = topic.lower()
    if "email" in t or "domain" in t:
        return f"College email domain: @{_CAMPUS['email_domain']}"
    if "support" in t or "help" in t or "contact" in t:
        return _CAMPUS["support"]
    if "location" in t or "where" in t:
        return f"{_CAMPUS['name']} is in {_CAMPUS['location']}."
    return f"{_CAMPUS['name']}, {_CAMPUS['location']}."


# --- registry ----------------------------------------------------------------
_REGISTRY: dict[str, Callable[..., str]] = {
    "calculator": calculator,
    "convert": convert,
    "current_datetime": current_datetime,
    "campus_info": campus_info,
}

SPECS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression.",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "e.g. '2*(3+4)/5'"}},
            "required": ["expression"]}}},
    {"type": "function", "function": {
        "name": "convert",
        "description": "Convert a value between common units (length/mass/temp/data).",
        "parameters": {"type": "object", "properties": {
            "value": {"type": "number"},
            "from_unit": {"type": "string"},
            "to_unit": {"type": "string"}},
            "required": ["value", "from_unit", "to_unit"]}}},
    {"type": "function", "function": {
        "name": "current_datetime",
        "description": "Get the current date and time in IST.",
        "parameters": {"type": "object", "properties": {
            "timezone": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "campus_info",
        "description": "Basic KSRMCE campus information.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string"}}, "required": []}}},
]


def run(name: str, args: dict[str, Any]) -> str:
    """Dispatch a validated tool call; never raises (returns an error string)."""
    fn = _REGISTRY.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return fn(**(args or {}))
    except TypeError:
        return f"Bad arguments for {name}: {args}"
    except Exception as e:  # noqa: BLE001
        return f"Tool {name} failed: {e}"


def names() -> list[str]:
    return list(_REGISTRY)
