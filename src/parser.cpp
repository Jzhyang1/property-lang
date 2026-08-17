#include "parser.h"
#include "interpret.h"
#include <strstream>

namespace pl {

Expression parse_expr(std::shared_ptr<State> state, istream& contents, int& next_char);

inline bool is_open_paren(int c) {
    return c == '(' || c == '{' || c == '[';
}
inline bool is_close_paren(int c) {
    return c == ')' || c == '}' || c == ']';
}
inline char matching_close_paren(int c) {
    return c == '(' ? ')' : c == '{' ? '}' : c == '[' ? ']' : '\0';
}

/**
 * Expects the next char in the arguments when called.
 * Keeps the first char that is not space in the arguments after call.
 */
inline void skip_spaces(istream& contents, int& next_char) {
    int cur_char = next_char;
    while(isspace(cur_char)) cur_char = contents.get();
    next_char = cur_char;
}

/**
 * Expects the first char (alnum) in the arguments when called.
 * Keeps the char after the identifier in the arguments after call.
 */
inline string parse_identifier(istream& contents, int& next_char) {
    std::stringstream ss;
    char cur_char = (char)next_char;
    do {
        ss << cur_char;
        cur_char = contents.get();
    } while (cur_char == '_' || isalnum(cur_char));
    next_char = cur_char;
    return ss.str();
}

/**
 * Expects the leading '"' to be consumed when called.
 * Consumes the trailing '"' after call.
 */
inline string parse_string(istream& contents) {
    std::stringstream ss;
    char cur_char = contents.get();
    while (cur_char != '"') {
        if (cur_char == '\\') {
            cur_char = contents.get();
            switch (cur_char)
            {
            case 'n': cur_char = '\n'; break;
            case 't': cur_char = '\t'; break;
            // defaults to keeping the same char
            }
        }
        ss << cur_char;
        cur_char = contents.get();
    }
    return ss.str();
}

/**
 * Expects the leading open-parenthesis to be consumed when called.
 * Consumes the close-parenthesis after call.
 */
inline void parse_tuple(std::shared_ptr<State> state, istream& contents, char end_char, tuple<Expression>& res) {
    int next_char = contents.get();
    while (next_char != end_char) {
        res.push_back(parse_expr(state, contents, next_char));
        if (next_char == end_char)
            return;
        if (next_char <= 0)
            throw "EOF reached before before all parenthesis closed";
        if (next_char != ',')
            throw "parenthesis mismatch";
        // we skip the comma and any spaces
        next_char = contents.get();
        skip_spaces(contents, next_char);
    }
}

/**
 * Expects the first character to be consumed and passed in when called.
 * Leaves the next char in next_char after call.
 * Requires the first token and parent to be passed in.
 * Extracts any compound clause if present.
 */
inline Expression parse_compound(std::shared_ptr<State> state, istream& contents, int& next_char, string token, Expression cur) {
    sourceline loc = contents.get_loc();
    if (is_open_paren(next_char)) {
        char paren = next_char;
        tuple<Expression> children; parse_tuple(state, contents, matching_close_paren(paren), children);
        next_char = contents.get();
        return std::make_shared<future<ExpressionNode>>(ExpressionNode{token, loc, cur, children, paren});
    } else {
        return std::make_shared<future<ExpressionNode>>(ExpressionNode{token, loc, cur});
    }
}

/**
 * Expects the first character to be consumed and passed in when called.
 * Leaves the next char in next_char after call if not terminated by (',' or ';'). Otherwise leaves ','
 */
inline Expression parse_prop(std::shared_ptr<State> state, istream& contents, int& next_char, Expression cur) {
    int cur_char = next_char;
    switch(cur_char) {
    case ';':
        cur = resolve_expression(state, cur);
    case ',':
        next_char = ',';
    case ')':
    case '}':
    case ']':
        return cur;
    case '.':
        next_char = contents.get();
        return resolve_expression(state, cur);
    case '"': {
        string str = parse_string(contents);
        next_char = contents.get();
        cur = parse_compound(state, contents, next_char, str, cur);
        return cur;
    }
    case '[': {
        tuple<Expression> children;
        parse_tuple(state, contents, ']', children);
        for (Expression child : children) {
            cur = resolve_expression(state, child, cur);   // append the resolved result of child to cur
        }
        next_char = contents.get();
        return cur;
    }
    default:
        if (cur_char <= 0) {
            // EOF
            next_char = cur_char;
            return cur;
        } else if (cur_char == '_' || isalnum(cur_char)) {
            std::string id = parse_identifier(contents, cur_char);
            next_char = cur_char;
            cur = parse_compound(state, contents, next_char, id, cur);
            return cur;
        } else {
            // generic operator -- we take a single char
            next_char = contents.get();
            cur = parse_compound(state, contents, next_char, std::string(1, cur_char), cur);
            return cur;
        }
    }
    next_char = contents.get();
    return cur;
}

/**
 * Leaves one of EOF, ',', ')', '}', ']' in next_char after call.
 */
Expression parse_expr(std::shared_ptr<State> state, istream& contents, int& next_char) {
    Expression cur{nullptr};
    int cur_char = next_char;
    skip_spaces(contents, cur_char);
    while (cur_char > 0 && cur_char != ',' && !is_close_paren(cur_char)) {
        cur = parse_prop(state, contents, cur_char, cur);
        skip_spaces(contents, cur_char);
    }
    next_char = cur_char;
    return cur;
}

void parse_pl_file(std::shared_ptr<State> state, istream& contents) {
    // we keep building up expressions and shipping them off
    int next_char;
    do {
        next_char = contents.get(); // skip commas
        parse_expr(state, contents, next_char);
    } while (next_char > 0);
}

}