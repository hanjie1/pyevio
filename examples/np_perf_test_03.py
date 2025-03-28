import numpy as np
import timeit

# Create test data
uniform_data = np.full(1000000, 42, dtype=np.int64)
non_uniform_data = np.full(1000000, 42, dtype=np.int64)
non_uniform_data[-1] = 43

def all_equal_1(lengths):
    return np.all(lengths == lengths[0])

def all_equal_2(lengths):
    return np.min(lengths) == np.max(lengths)

def all_equal_3(lengths):
    return len(np.unique(lengths)) == 1

def all_equal_4(lengths):
    return np.std(lengths) == 0

def all_equal_5(lengths):
    return len(set(lengths)) == 1


# Test functions
def performance():
    methods = [all_equal_1, all_equal_2, all_equal_3, all_equal_4, all_equal_5]

    print("Testing with uniform data (all elements equal):")
    for i, method in enumerate(methods, 1):
        time = timeit.timeit(lambda: method(uniform_data), number=100)
        print(f"Method {i}: {time:.6f} seconds")

    print("\nTesting with non-uniform data (last element different):")
    for i, method in enumerate(methods, 1):
        time = timeit.timeit(lambda: method(non_uniform_data), number=100)
        print(f"Method {i}: {time:.6f} seconds")

performance()