import datetime
import ast
import operator

ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

def _safe_eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in ALLOWED_OPERATORS:
            raise ValueError("Unsupported operation")
        return ALLOWED_OPERATORS[op_type](_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in ALLOWED_OPERATORS:
            raise ValueError("Unsupported operation")
        return ALLOWED_OPERATORS[op_type](_safe_eval(node.operand))
    else:
        raise ValueError("Unsupported expression")

def calculator(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)
    except Exception as e:
        return f"Error: could not calculate ({e})"

def get_current_datetime() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic math expression (add, subtract, multiply, divide, power).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression, e.g. '2 + 2 * 3'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current date and time.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

AVAILABLE_FUNCTIONS = {
    "calculator": calculator,
    "get_current_datetime": get_current_datetime,
}