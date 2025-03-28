import numpy as np
import timeit

# Generate an array of random data.
# Increase N to see performance differences more clearly.
N = 5_000_000
lengths = np.random.randint(0, 2, size=N, dtype=np.int64)
# For a test case with all-equal data, try:
# lengths = np.zeros(N, dtype=np.int64)

def all_equal_to_first(arr):
    return np.all(arr == arr[0])

def min_max_equal(arr):
    return arr.min() == arr.max()

def unique_size_one(arr):
    return np.unique(arr).size == 1

# Warm up each function once:
_ = all_equal_to_first(lengths)
_ = min_max_equal(lengths)
_ = unique_size_one(lengths)

# Time them:
t1 = timeit.timeit("all_equal_to_first(lengths)",
                   number=5, globals=globals())
t2 = timeit.timeit("min_max_equal(lengths)",
                   number=5, globals=globals())
t3 = timeit.timeit("unique_size_one(lengths)",
                   number=5, globals=globals())

print("Compare all==arr[0]:", t1)
print("Compare min==max   :", t2)
print("Unique size == 1   :", t3)
