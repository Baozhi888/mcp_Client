# server.py
from mcp.server.fastmcp import FastMCP
import ast
import logging
import math
import operator
import random

logger = logging.getLogger('test_mcp')

# Create an MCP server
mcp = FastMCP("Calculator")


MAX_EXPRESSION_LENGTH = 500
MAX_AST_NODES = 80
MAX_ABS_NUMBER = 10 ** 100
MAX_POWER_EXPONENT = 1000
MAX_RESULT_REPR = 2000

_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_MATH_FUNCTIONS = {
    name: getattr(math, name)
    for name in [
        "acos", "asin", "atan", "atan2", "ceil", "copysign", "cos", "degrees",
        "erf", "erfc", "exp", "expm1", "fabs", "floor", "fmod", "frexp",
        "fsum", "gamma", "hypot", "isclose", "isfinite", "isinf", "isnan",
        "ldexp", "lgamma", "log", "log10", "log1p", "log2", "modf", "pow",
        "radians", "remainder", "sin", "sinh", "sqrt", "tan", "tanh", "trunc",
    ]
}

_RANDOM_FUNCTIONS = {
    name: getattr(random, name)
    for name in ["random", "uniform", "randint", "randrange"]
}

_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}


class SafeExpressionError(ValueError):
    pass


def _check_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafeExpressionError("Only numeric expressions are allowed")
    if isinstance(value, (int, float)) and abs(value) > MAX_ABS_NUMBER:
        raise SafeExpressionError("Numeric value is too large")
    return value


def _resolve_call(node):
    if isinstance(node, ast.Name):
        if node.id in _MATH_FUNCTIONS:
            return _MATH_FUNCTIONS[node.id]
        if node.id in _RANDOM_FUNCTIONS:
            return _RANDOM_FUNCTIONS[node.id]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "math" and node.attr in _MATH_FUNCTIONS:
            return _MATH_FUNCTIONS[node.attr]
        if node.value.id == "random" and node.attr in _RANDOM_FUNCTIONS:
            return _RANDOM_FUNCTIONS[node.attr]
    raise SafeExpressionError("Function is not allowed")


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        return _check_number(node.value)

    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise SafeExpressionError(f"Name is not allowed: {node.id}")

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _check_number(_UNARY_OPS[type(node.op)](_eval_node(node.operand)))

    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > MAX_POWER_EXPONENT or abs(left) > 10 ** 6:
                raise SafeExpressionError("Power operation is too large")
        return _check_number(_BINARY_OPS[type(node.op)](left, right))

    if isinstance(node, ast.Call):
        if node.keywords:
            raise SafeExpressionError("Keyword arguments are not allowed")
        if len(node.args) > 5:
            raise SafeExpressionError("Too many function arguments")
        func = _resolve_call(node.func)
        args = [_eval_node(arg) for arg in node.args]
        return _check_number(func(*args))

    raise SafeExpressionError(f"Expression type is not allowed: {type(node).__name__}")


def safe_calculate(expression: str):
    if not isinstance(expression, str) or not expression.strip():
        raise SafeExpressionError("Expression is empty")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise SafeExpressionError("Expression is too long")

    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise SafeExpressionError("Expression is too complex")
    return _eval_node(tree)


# Add an addition tool
@mcp.tool()
def calculator(python_expression: str) -> dict:
    """Calculate a safe numeric expression. Common math functions and selected random functions are available."""
    try:
        result = safe_calculate(python_expression)
        result_preview = repr(result)
        if len(result_preview) > MAX_RESULT_REPR:
            raise SafeExpressionError("Result is too large")
        logger.info("Calculated formula: %s, result: %s", python_expression[:120], result_preview[:120])
        return {"success": True, "result": result}
    except Exception as exc:
        logger.warning("Rejected formula: %s (%s)", str(python_expression)[:120], exc)
        return {"success": False, "error": str(exc)}

# Start the server
if __name__ == "__main__":
    mcp.run(transport="stdio")
