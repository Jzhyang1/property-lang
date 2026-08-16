#ifndef ISTREAM_H
#define ISTREAM_H

#include <cstdio>
#include <iostream>

namespace pl {

struct sourceline {
    std::string file;
    std::uint64_t row, col; // 0-indexed
};

class istream {
    std::istream& stream;
    sourceline loc;

public:
    istream(const std::string& file, std::istream& stream): loc{file, 0l, 0l}, stream(stream) {}

    int get() {
        int ret = stream.get();
        if (ret == '\n') {
            loc.row += 1;
            loc.col = 0;
        } else {
            loc.col += 1;
        }
        return ret;
    }

    inline sourceline get_loc() {
        return loc;
    }

};

}

#endif // ISTREAM_H