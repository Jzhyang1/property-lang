from typing import Callable
from constants import Definition, Scope, Expression, Property, Token
from definitions import register_definition
from errors import perror, pwarning

def integer_binary_op(op: str) -> Callable[[Callable[[int, int],int]], None]:
    def wrapper(func: Callable[[int, int], int]) -> None:
        def apply(lhs: Expression, rhs: Expression) -> Expression:
            ival = rhs.force_get_property('integer')
            idst = lhs.force_get_property('integer')
            ires = idst.copy()
            ires.is_association = True
            ires.associated_value = func(idst.associated_value, ival.associated_value)
            return lhs.replace_property('integer', ires)
        register_definition(op, ['integer'], ['operand'])(apply)
    return wrapper

@integer_binary_op('+')
def add(lhs_val: int, rhs_val: int) -> int:
    return lhs_val + rhs_val

@integer_binary_op('-')
def subtract(lhs_val: int, rhs_val: int) -> int:
    return lhs_val - rhs_val

@integer_binary_op('*')
def multiply(lhs_val: int, rhs_val: int) -> int:
    return lhs_val * rhs_val

@integer_binary_op('/')
def divide(lhs_val: int, rhs_val: int) -> int:
    if rhs_val == 0:
        perror(f"dividing by 0")
    return lhs_val // rhs_val

@integer_binary_op('==')
def equal(lhs_val: int, rhs_val: int) -> int:
    return int(lhs_val == rhs_val)

@integer_binary_op('!=')
def not_equal(lhs_val: int, rhs_val: int) -> int:
    return int(lhs_val != rhs_val)

@integer_binary_op('<')
def less_than(lhs_val: int, rhs_val: int) -> int:
    return int(lhs_val < rhs_val)

@integer_binary_op('<=')
def less_than_or_equal(lhs_val: int, rhs_val: int) -> int:
    return int(lhs_val <= rhs_val)

@integer_binary_op('>')
def greater_than(lhs_val: int, rhs_val: int) -> int:
    return int(lhs_val > rhs_val)

@integer_binary_op('>=')
def greater_than_or_equal(lhs_val: int, rhs_val: int) -> int:
    return int(lhs_val >= rhs_val)