#include "interpret.h"
#include <ctime>

namespace pl {

inline bool should_offload(const DefinitionBody& def, Expression expr) {
    return false;
    // return def.get_measurement() & 1;  // pretty much random right now
}

/**
 * When we resolve a definition, we *apply* the definition and record the time.
 * The actual definitions are found in definitions.cpp
 */
inline Expression resolve_sync(State& state, const DefinitionBody& def, Expression expr, Expression parent) {
    auto start_time = std::chrono::steady_clock::now();
    Expression ret = def.apply(state, expr);
    auto end_time = std::chrono::steady_clock::now();
    def.track_measurement((end_time - start_time).count());
    return ret;
}

Expression resolve_expression(std::shared_ptr<State> state, Expression expr, Expression parent){
    // this will run asynchronously if the job is too long
    // right now this is just done randomly
    const DefinitionBody& def = state->defs.find_nearest(expr).first->get_body();
    if (should_offload(def, expr)) {
        promise<ExpressionNode> p;
        std::future<ExpressionNode> res = p.get_future();
        std::thread([state, &def, expr, parent, p = std::move(p)] () mutable {
            p.set_value(resolve_sync(*state.get(), def, expr, parent)->get());
        }).detach();
        return std::make_shared<future<ExpressionNode>>(res.share());
    } else {
        return resolve_sync(*state.get(), def, expr, parent);
    }
}

}