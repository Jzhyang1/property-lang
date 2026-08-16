SRC?=../src/
GCC?=g++
CPP_FLAGS?=-std=c++17

SECONDARY: */.output

%.out: %.cpp
	@${GCC} ${CPP_FLAGS} $< -o $@

%/.output: %/tester.out
	@$< > $*/.output

%/.test: %/.output %/expected.txt %/tester.out
	@diff $*< $*/expected.txt > $@