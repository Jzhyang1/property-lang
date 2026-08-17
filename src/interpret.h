#ifndef INTERPRET_H
#define INTERPRET_H

#include <functional>
#include <map>
#include <memory>
#include "parser.h"
#include "tuple.h"

namespace pl {

struct DefinitionMetadata {
    std::uint64_t time_sum = 0;
    std::uint64_t time_min = 0, time_max = 0;
    std::uint64_t time_samples = 0;
};

class DefinitionBody {
    tuple<Expression> body;
    std::unique_ptr<DefinitionMetadata> metadata = std::make_unique<DefinitionMetadata>();
public:
    std::function<Expression(State&, Expression, const tuple<Expression>&)> _apply;

    DefinitionBody() = default;
    DefinitionBody(std::function<Expression(State&, Expression, const tuple<Expression>&)> apply): _apply(apply) {}
    DefinitionBody(std::function<Expression(State&, Expression, const tuple<Expression>&)> apply, tuple<Expression> body): _apply(apply), body(body) {}

    inline Expression apply(State& state, Expression expr) const {
        return _apply(state, expr, body);
    }
    inline void track_measurement(std::uint64_t time) const {
        metadata->time_sum += time;
        metadata->time_min = std::min(metadata->time_min, time);
        metadata->time_max = std::max(metadata->time_max, time);
        metadata->time_samples++;
    }
    inline std::uint64_t get_measurement() const {
        return metadata->time_min;
    }
};

class Definition {
    std::map<string, Definition*> deeper;
    promise<DefinitionBody> setbody;
    future<DefinitionBody> body; // present if defined

public:
    Definition(DefinitionBody&& body): body(std::move(body)) {}
    Definition(): body(setbody.get_future()) {}
    ~Definition() {
        for (auto p : deeper) {
            delete p.second;
        }
    }

    /**
     * Sometimes we are running in parallel and want to get a variable
     * that another thread has yet to define, so we reserve the place and wait
     */
    inline std::pair<Definition*, Expression> find_nearest(Expression expr) {
        Definition* cur_def = this;
        Expression cur_expr = expr;
        while (cur_expr != nullptr) {
            string token = cur_expr->get().token;
            auto def = cur_def->deeper.find(token);
            if (def == cur_def->deeper.end()) {
                break; // no further level of definition
            }
            cur_def = def->second;
            cur_expr = cur_expr->get().parent;
        }
        return {cur_def, cur_expr};
    }

    inline Definition* reserve(Expression expr) {
        auto [cur_def, cur_expr] = find_nearest(expr);

        while (cur_expr != nullptr) {
            Definition* new_def = new Definition{};
            cur_def->deeper.insert({cur_expr->get().token, new_def});
            cur_def = new_def;
            cur_expr = cur_expr->get().parent;
        }
        return cur_def;
    }

    /**
     * This is used for built-in definitions.
     * Props should be listed in reverse (i.e. the first prop listed is the prop that is defined)
     */
    inline Definition* reserve(std::initializer_list<string> props) {
        Definition* cur_def = this;
        auto iter = props.begin();
        while (iter != props.end()) {
            auto def = cur_def->deeper.find(*iter);
            if (def == cur_def->deeper.end()) {
                break; // no further level of definition
            }
            cur_def = def->second;
            iter++;
        }
        while (iter != props.end()) {
            Definition* new_def = new Definition{};
            cur_def->deeper.insert({*iter, new_def});
            cur_def = new_def;
            iter++;
        }
        return cur_def;
    }

    inline void set_body(DefinitionBody&& body) {
        setbody.set_value(std::move(body));
    }

    inline const DefinitionBody& get_body() {
        return body.get();
    }
};

struct State {
    std::shared_ptr<State> parent;
    Definition defs;
    Expression context;
};

/**
 * Resolves expr, possibly asynchronously.
 * Appends the result of resolving expr to parent when call exits.
 */
Expression resolve_expression(std::shared_ptr<State> state, Expression expr, Expression parent = Expression{nullptr});


/**
 * Builtin definitions. See definitions.cpp
 */
void register_builtins(std::shared_ptr<State> state);

}

#endif // INTERPRET_H