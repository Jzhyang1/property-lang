#ifndef PARSER_H
#define PARSER_H

#include <cstdio>
#include <iostream>
#include <memory>
#include "queue.h"
#include "string.h"
#include "tuple.h"
#include "istream.h"
#include "future.h"

namespace pl {

struct ExpressionNode {
    string token;
    sourceline loc;
    std::shared_ptr<future<ExpressionNode>> parent;
    tuple<std::shared_ptr<future<ExpressionNode>>> children;
    char children_paren;

    inline std::shared_ptr<ExpressionNode> replace(std::shared_ptr<ExpressionNode> replacement) {
        if (replacement->parent.get() != nullptr) throw "replacement is dirty";

        replacement->parent = parent;
        return replacement;
    }
};
using Expression = std::shared_ptr<future<ExpressionNode>>;

struct State;   // forward declare; actual implementation is in interpret.h

void parse_pl_file(std::shared_ptr<State> state, istream& contents);

}

#endif // PARSER_H