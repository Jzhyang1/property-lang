#include "interpret.h"

namespace pl {
// We match the structure of Expression(Expression, const tuple<Expression>&)

struct IntExpressionNode : public ExpressionNode {
    unsigned long value;
    IntExpressionNode(const ExpressionNode& ref): ExpressionNode(ref), value(std::stoul(ref.token)) {
        token = "int";
    }
};

/**
 * This is used when no definition matches.
 * This can be 2 cases:
 * - user code has an issue
 * - the value being resolved is an int and should be replaced with a IntExpressionNode
 */
Expression resolve_unmatched(Expression expr, const tuple<Expression>& body) {
    try {
        return std::make_shared<future<ExpressionNode>>(std::make_unique<IntExpressionNode>(expr->get()));
    } catch (const std::invalid_argument& e) {
        std::cerr << "Unable to resolve " << expr->get().token << std::endl;
    }
    return expr;
}

Expression resolve_print_int(Expression expr, const tuple<Expression>& body) {
    IntExpressionNode* iexpr = (IntExpressionNode*)(&expr->get().parent->get());
    std::cout << iexpr->value << std::endl;
    return expr;
}

Expression resolve_print(Expression expr, const tuple<Expression>& body) {
    std::cout << expr->get().parent->get().token << std::endl;
    return expr;
}


void register_builtins(std::shared_ptr<State> state) {
    state->defs.reserve({})->set_body(DefinitionBody{resolve_unmatched});
    state->defs.reserve({"print"})->set_body(DefinitionBody{resolve_print});
    state->defs.reserve({"print", "int"})->set_body(DefinitionBody{resolve_print_int});
}

} // pl