import numpy as np
import timeit
import matplotlib.pyplot as plt # For plotting results (optional)

# Assume 'events' is a list/iterable of objects with a 'length' attribute
# Example placeholder data:
class Event:
    def __init__(self, length):
        self.length = length

# Create some example event lists for testing
events_all_same = [Event(100) for _ in range(100000)]
events_diff_end = [Event(100) for _ in range(99999)] + [Event(101)]
events_diff_start = [Event(101)] + [Event(100) for _ in range(99999)]
events_empty = []
events_single = [Event(50)]

# --- Methods to Check Equality ---

def check_all_equal_v1(arr):
    """Compares all elements to the first element using np.all()."""
    if arr.size < 2: # Empty or single-element arrays are considered "all same"
        return True
    return np.all(arr == arr[0])

def check_all_equal_v2(arr):
    """Checks if the min and max values are equal."""
    if arr.size < 2:
        return True
    # Using np.ptp (peak-to-peak) is concise for min == max check
    # return np.ptp(arr) == 0
    # Or explicitly:
    return np.min(arr) == np.max(arr)

def check_all_equal_v3(arr):
    """Checks if the number of unique elements is 0 or 1."""
    # np.unique handles empty arrays correctly (returns empty array, size 0)
    # and single-element arrays (returns array with 1 element, size 1)
    return np.unique(arr).size <= 1

# --- Performance Test Setup ---

test_scenarios = {
    "large_all_same": events_all_same,
    "large_diff_end": events_diff_end,
    "large_diff_start": events_diff_start,
    "small_all_same": [Event(20)] * 10,
    "small_diff_end": [Event(20)] * 9 + [Event(21)],
    "small_diff_start": [Event(21)] + [Event(20)] * 9,
    "empty": events_empty,
    "single": events_single
}

results = {}
n_runs = 100 # Number of times to execute the core statement within one timeit call
n_repeats = 5 # Number of times to repeat the timeit call for stability

print("Starting performance tests...")

for name, event_list in test_scenarios.items():
    print(f"\n--- Testing Scenario: {name} ---")
    # Create the numpy array - include this step outside the timed loop
    # as the user already has the array.
    lengths_arr = np.array([event.length for event in event_list], dtype=np.int64)
    results[name] = {}

    for func in [check_all_equal_v1, check_all_equal_v2, check_all_equal_v3]:
        func_name = func.__name__
        try:
            # Use globals to pass the array and function to timeit's environment
            global_vars = {'np': np, func_name: func, 'data': lengths_arr}
            setup_code = f"import numpy as np; from __main__ import {func_name}; arr = data"

            times = timeit.repeat(stmt=f"{func_name}(arr)",
                                  setup=setup_code,
                                  globals=global_vars,
                                  repeat=n_repeats,
                                  number=n_runs)

            # Calculate time per single execution
            min_avg_time = min(times) / n_runs
            results[name][func_name] = min_avg_time
            print(f"{func_name}: {min_avg_time*1e6:.2f} microseconds per run") # Show in microseconds

            # Verify correctness (optional)
            # print(f"  -> Result: {func(lengths_arr)}")

        except Exception as e:
            print(f"Error timing {func_name} on {name}: {e}")
            results[name][func_name] = float('inf') # Indicate error


print("\n--- Performance Summary (microseconds per run) ---")
# Print results in a more tabular format
header = ["Scenario"] + [f.__name__ for f in [check_all_equal_v1, check_all_equal_v2, check_all_equal_v3]]
print(f"{header[0]:<20}" + "".join([f"{h:<22}" for h in header[1:]]))
print("-" * (20 + 22 * (len(header)-1)))
for name, timings in results.items():
    row = f"{name:<20}"
    for h in header[1:]:
        time_us = timings.get(h, float('inf')) * 1e6 # Convert to microseconds
        row += f"{time_us:<22.2f}"
    print(row)

# --- Analysis (General Observations - Exact results depend on hardware/versions) ---

# 1. check_all_equal_v1 (np.all(arr == arr[0])):
#    - Often very fast, especially if a difference is found early (short-circuiting).
#    - If all elements *are* the same, it still needs to compare every element.
#    - Requires handling the empty/single element case explicitly or carefully.

# 2. check_all_equal_v2 (np.min == np.max or np.ptp == 0):
#    - Needs to scan the entire array to find the minimum and maximum.
#    - Can be quite efficient as min/max operations are highly optimized in NumPy.
#    - Requires handling the empty case explicitly as np.min/np.max raise errors on empty arrays. np.ptp also errors.

# 3. check_all_equal_v3 (np.unique(arr).size <= 1):
#    - Very concise code.
#    - Handles empty/single element cases gracefully.
#    - `np.unique` typically involves sorting or hashing, which can be significantly slower than simple comparisons or min/max, *especially* if all elements are the same or the array is large. It might be faster if there are many different values early on.

# --- Conclusion & Recommendation ---

# Based on typical performance characteristics:
# - For **general-purpose use and often the best performance**, `check_all_equal_v1` (using `np.all(arr == arr[0])`) is a strong contender, especially if differences are expected early in the array.
# - `check_all_equal_v2` (using `np.min == np.max` or `np.ptp == 0`) can be competitive, particularly if the array needs to be scanned entirely anyway. Its performance relative to v1 can vary. `np.ptp` is very readable.
# - `check_all_equal_v3` (using `np.unique`) is the most concise but often the **slowest**, especially for large arrays where all elements are indeed the same.
