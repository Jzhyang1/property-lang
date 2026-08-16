#ifndef FUTURE_H
#define FUTURE_H

#include <future>
#include <atomic>

namespace pl {

template<typename T>
class future {
    // we have 2 options: the future is constructed with the value
    // or we need to wait for the value
    const bool use_cache;
    const std::unique_ptr<T> cache;
    std::shared_future<T> getter;

public:
    future(std::unique_ptr<T>&& val): use_cache(true), cache(std::move(val)) {};
    future(const T& val): use_cache(true), cache(std::make_unique<T>(val)) {};
    future(T&& val): use_cache(true), cache(std::make_unique<T>(std::move(val))) {};
    future(std::shared_future<T> val): use_cache(false), cache(), getter(val) {};

    inline const T& get() {
        return use_cache ? *cache : getter.get();
    }
};


template<typename T>
class promise {
    std::promise<T> setter;

public:
    std::future<T> get_future() {
        return setter.get_future();
    }

    void set_value(const T& value) {
        setter.set_value(value);
    }

    void set_value(T&& value) {
        setter.set_value(std::move(value));
    }
};

}

#endif // FUTURE_H