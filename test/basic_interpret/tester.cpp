#include "../../src/interpret.cpp"
#include "../../src/definitions.cpp"

int main() {
    std::shared_ptr<pl::State> state = std::make_shared<pl::State>();
    pl::register_builtins(state);

    {
        // "hello world" print;
        pl::Expression print = std::make_shared<pl::future<pl::ExpressionNode>>(
            pl::ExpressionNode{
                "print", {},
                std::make_shared<pl::future<pl::ExpressionNode>>(pl::ExpressionNode{"hello world"})
            }
        );
        pl::resolve_expression(state, print, nullptr);
    }

    {
        // 1.print;
        pl::Expression raw1 = std::make_shared<pl::future<pl::ExpressionNode>>(
            pl::ExpressionNode{"1"}
        );
        pl::Expression int1 = pl::resolve_expression(state, raw1, nullptr);
        std::cout << int1->get().token << std::endl;
        pl::Expression print2 = std::make_shared<pl::future<pl::ExpressionNode>>(
            pl::ExpressionNode{"print", {}, int1}
        );
        pl::resolve_expression(state, print2, nullptr);
    }

    return 0;
}