#define INTERPRET_H // hide interpreter
#include "../../src/parser.h"

// ===============================================================
// Mockup of interpreter (which we usually process asynchronously)

namespace pl {

class Definition {
public:
    inline std::pair<Definition*, Expression> find_nearest(Expression expr) {
        return {this, expr};
    }
    inline Definition* reserve(Expression expr) {
        return this;
    }
    inline const Definition& get_body() {
        return *this;
    }
};
using DefinitionBody = Definition;

struct State {
    std::shared_ptr<State> parent;
    Definition defs;
    Expression context;
};

Expression resolve_expression(std::shared_ptr<State> state, Expression expr, Expression parent = Expression{nullptr}) {
    std::cout << expr->get().token << std::endl;
    return expr;
}

}

// ===================
// Actual testing code

#include "../../src/parser.cpp"

int main() {
    {
        // test parsing basic stuff
        std::cout << "[TEST] Parse Identifiers" << std::endl;
        std::istringstream srcraw{"hello world"};
        pl::istream src{"file", srcraw};

        int next_char = src.get();
        auto hello = pl::parse_identifier(src, next_char);
        auto world = pl::parse_identifier(src, next_char);

        std::cout << hello << " " << world << std::endl;
    }
    {
        // test parsing basic stuff
        std::cout << "[TEST] Parse Strings" << std::endl;
        std::istringstream srcraw{"\"hello\" \"world\""};
        pl::istream src{"file", srcraw};

        int next_char = src.get();
        auto hello = pl::parse_string(src);
        next_char = src.get();
        pl::skip_spaces(src, next_char);    // will consume the '"' char
        auto world = pl::parse_string(src);

        std::cout << hello << " " << world << std::endl;
    }
    {
        // test parsing simple properties
        std::cout << "[TEST] Parse Props" << std::endl;
        std::istringstream srcraw{"\"hello\" world"};
        pl::istream src{"file", srcraw};
        std::shared_ptr<pl::State> state = std::make_shared<pl::State>();

        int next_char = src.get();
        auto hello = pl::parse_prop(state, src, next_char, nullptr);
        pl::skip_spaces(src, next_char);
        auto world = pl::parse_prop(state, src, next_char, nullptr);
        std::cout << hello->get().token << " " << world->get().token << std::endl;
    }
    {
        // test parsing compound properties
        std::cout << "[TEST] Parse Compound Props" << std::endl;
        std::istringstream srcraw{"\"hello\"(first) world(second, third)"};
        pl::istream src{"file", srcraw};
        std::shared_ptr<pl::State> state = std::make_shared<pl::State>();

        int next_char = src.get();
        auto hello = pl::parse_prop(state, src, next_char, nullptr);
        pl::skip_spaces(src, next_char);
        auto world = pl::parse_prop(state, src, next_char, nullptr);
        std::cout << hello->get().token << " " << world->get().token << std::endl;
        std::cout << hello->get().children[0]->get().token << " " <<
            world->get().children[0]->get().token << " " <<
            world->get().children[1]->get().token << std::endl;
    }
    {
        // test parsing expression
        std::cout << "[TEST] Parse Expression" << std::endl;
        std::istringstream srcraw{"\"hello\"(first) world(second, third)"};
        pl::istream src{"file", srcraw};
        std::shared_ptr<pl::State> state = std::make_shared<pl::State>();

        int next_char = src.get();
        auto world = pl::parse_expr(state, src, next_char);
        auto hello = world->get().parent;
        std::cout << hello->get().token << " " << world->get().token << std::endl;
        std::cout << hello->get().children[0]->get().token << " " <<
            world->get().children[0]->get().token << " " <<
            world->get().children[1]->get().token << std::endl;
    }
    {
        // test resolving expression
        std::cout << "[TEST] Resolve Expression" << std::endl;
        std::istringstream srcraw{"\"hello\".world;"};
        pl::istream src{"file", srcraw};
        std::shared_ptr<pl::State> state = std::make_shared<pl::State>();

        int next_char = src.get();
        auto world = pl::parse_expr(state, src, next_char);
        auto hello = world->get().parent;
        std::cout << hello->get().token << " " << world->get().token << std::endl;
    }
}