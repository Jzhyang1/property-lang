#include "interpret.h"
#include <map>

namespace pl {
// We match the structure of Expression(Expression, const tuple<Expression>&)

struct IntExpressionNode : public ExpressionNode {
    unsigned long value;
    IntExpressionNode(const ExpressionNode& ref): ExpressionNode(ref), value(std::stoul(ref.token)) {
        token = "int";
    }
};

struct StructExpressionNode: public ExpressionNode {
    std::map<string, Expression> fields;
};

/**
 * This is used when no definition matches.
 * This can be 2 cases:
 * - user code has an issue
 * - the value being resolved is an int and should be replaced with a IntExpressionNode
 */
Expression resolve_unmatched(State& state, Expression expr, const tuple<Expression>& body) {
    try {
        return std::make_shared<future<ExpressionNode>>(std::make_unique<IntExpressionNode>(expr->get()));
    } catch (const std::invalid_argument& e) {
        std::cerr << "Unable to resolve ";
        Expression temp = expr;
        while (temp != nullptr) {
            std::cerr << temp->get().token << " ";
            temp = temp->get().parent;
        }
        std::cerr << std::endl;
    }
    return expr;
}

Expression resolve__def_(State& state, Expression expr, const tuple<Expression>& body) {
    // TODO handle '.' in body
    const Expression res = body[body.size() - 1];
    return res;
}

Expression resolve_def(State& state, Expression expr, const tuple<Expression>& body) {
    Expression props = expr->get().parent;
    state.defs.reserve(props)->set_body(DefinitionBody{resolve__def_, expr->get().children});
    return expr;
}

Expression resolve_print_int(State& state, Expression expr, const tuple<Expression>& body) {
    IntExpressionNode* iexpr = (IntExpressionNode*)(&expr->get().parent->get());
    std::cout << iexpr->value << std::endl;
    return expr;
}

Expression resolve_print(State& state, Expression expr, const tuple<Expression>& body) {
    std::cout << expr->get().parent->get().token << std::endl;
    return expr;
}

/**
 * Resolves the user-defined struct (e.g. coords). This creates a copy of
 * the expr with additional fields.
 */
Expression resolve__struct_(State& state, Expression expr, const tuple<Expression>& body) {
    return std::make_shared<future<ExpressionNode>>(StructExpressionNode{});
}

Expression resolve__struct___field_(State& state, Expression expr, const tuple<Expression>& body) {
    string field = expr->get().token;
    // we assume struct is the parent
    Expression struct_expr = expr->get().parent;
    StructExpressionNode* val = (StructExpressionNode*)&struct_expr->get();
    return val->fields[field];
}

Expression resolve__struct___field__def(State& state, Expression expr, const tuple<Expression>& body) {
    Expression rhs = expr->get().children[0];
    Expression parent = expr->get().parent;
    string field = expr->get().token;
    // we assume struct is the parent
    Expression struct_expr = expr->get().parent;
    StructExpressionNode* val = (StructExpressionNode*)&struct_expr->get();
    return val->fields[field] = rhs;
}

Expression resolve_struct(State& state, Expression expr, const tuple<Expression>& body) {
    Expression struct_name = expr->get().parent;
    
    // We evaluate the body up-front into
    // <struct_name> <eval(body[0])>
    // <struct_name> <eval(body[0])> def
    // ...
    for (Expression expr : body) {
        state.defs.reserve(expr)->reserve(struct_name)->set_body(DefinitionBody{
            resolve__struct___field_
        });

        state.defs.reserve(std::make_shared<future<ExpressionNode>>(ExpressionNode{"def"}))
            ->reserve(expr)->reserve(struct_name)->set_body(DefinitionBody{
            resolve__struct___field__def
        });
    }

    state.defs.reserve(struct_name)->set_body(DefinitionBody{resolve__struct_});
    return expr;
}


void register_builtins(std::shared_ptr<State> state) {
    state->defs.reserve({})->set_body(DefinitionBody{resolve_unmatched});
    state->defs.reserve({"def"})->set_body(DefinitionBody{resolve_def});
    state->defs.reserve({"struct"})->set_body(DefinitionBody{resolve_struct});
    state->defs.reserve({"print"})->set_body(DefinitionBody{resolve_print});
    state->defs.reserve({"print", "int"})->set_body(DefinitionBody{resolve_print_int});
}

} // pl