#include "parser.h"
#include "interpret.h"
#include <fstream>
#include <iostream>

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "No file provided" << std::endl;
        return 1;
    }
    std::shared_ptr<pl::State> state = std::make_shared<pl::State>();
    pl::register_builtins(state);

    std::ifstream stream{argv[1]};
    pl::istream contents{argv[1], stream};
    pl::parse_pl_file(state, contents);
    return 0;
}