#ifndef QUEUE_H
#define QUEUE_H

#include <queue>
#include <mutex>

namespace pl {

// Simplest worker queue to get started.
// Aim to get a fast SPMC queue later

template <typename T>
class WorkerQueue {
    std::mutex mu;
    std::queue<T> tasks;
    std::size_t max_elements;

public:
    WorkerQueue(size_t max_elements): max_elements(max_elements) {}

    inline void push(T arg) {
        std::lock_guard<std::mutex> _{mu};
        tasks.push(arg);
    }

    inline bool try_pop(T& res) {
        std::lock_guard<std::mutex> _{mu};
        res = tasks.front();
        tasks.pop();
    }
};

}

#endif // QUEUE_H