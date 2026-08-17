SRC?=../src/
GCC?=g++
CPP_FLAGS?=-std=c++17
MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ROOT_DIR := $(realpath $(MK_DIR)../)

H_FILES := $(wildcard ${ROOT_DIR}/src/*.h)
CPP_FILES := $(wildcard ${ROOT_DIR}/src/*.cpp)

SECONDARY: */.output

interpreter.out: ${H_FILES} ${CPP_FILES}
	@${GCC} ${CPP_FLAGS} ${CPP_FILES} -o interpreter.out

%.out: %.cpp
	@${GCC} ${CPP_FLAGS} $< -o $@

%/.output: %/tester.lang interpreter.out
	@interpreter.out $< > $*/.output

%/.output: %/tester.out
	@$< > $*/.output

%/.test: %/.output %/expected.txt %/tester.out
	@diff $*< $*/expected.txt > $@