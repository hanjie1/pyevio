#!/usr/bin/e    nv python3
"""
Example script demonstrating direct loading of EVIO events into NumPy arrays
for efficient processing without the overhead of creating Event objects.
"""

import numpy as np
import time
import sys
import os
from pyevio import EvioFile
from pyevio.utils import print_offset_hex


def direct_events_loading2(filename, start_event=0, end_event=100000, event_size_bytes=88, endian='>'):
    print(f"Loading events {start_event}-{end_event-1} from {filename}")
    print(f"Assuming fixed event size of {event_size_bytes} bytes")

    # Calculate event size in 32-bit words
    event_size_words = event_size_bytes // 4
    print(f"Event size: {event_size_words} words")

    with EvioFile(filename) as evio_file:
        # Get first record for demonstration
        record = evio_file.get_record(2)

        # Get event offsets directly
        t0 = time.time()
        event_infos = record.get_event_offsets(start_event, end_event)
        t1 = time.time()
        print(f"Got {len(event_infos)} event offsets in {(t1-t0)*1000:.2f} ms")

        prev_delta = event_infos[1][0] - event_infos[0][0]
        for i in range (1, len(event_infos)):
            new_delta = event_infos[i][0] - event_infos[i-1][0]
            if new_delta != prev_delta:
                print(f"i = {i} New delta {prev_delta} Old delta {new_delta} ioff: {event_infos[i][0]} isize:{event_infos[i][1]}  i-1{event_infos[i-1][0]} {event_infos[i-1][1]}")
                prev_delta = new_delta

                print_offset_hex(evio_file.mm, event_infos[i-1][0], event_infos[i-1][1]//4)


        start_offset, start_size = event_infos[0]
        end_offset, end_size = event_infos[-1]

        t0 = time.time()
        event_data = np.frombuffer(
                evio_file.mm[start_offset:end_offset + end_size],
             dtype=np.dtype(np.uint32).newbyteorder('>' if endian == '>' else '<')
        )
        t1 = time.time()
        print(f"Got frombuffer in {(t1-t0)*1000:.2f} ms")

        event_word_size = end_size//4

        t0 = time.time()
        event_data = np.reshape(event_data,  (len(event_data) // event_word_size, event_word_size))
        t1 = time.time()
        print(f"Got reshape in {(t1-t0)*1000:.2f} ms")

        print(f"=== Reshaped array: shape = {event_data.shape} ===")
        # for row in event_data:
        #     # For each row, join columns with a space, each printed as 16-digit hex:
        #     print(" ".join(f"{val:08X}" for val in row))

def direct_events_loading(filename, start_event=0, end_event=100, event_size_bytes=88):
    """
    Load events directly into NumPy arrays for efficient processing.

    Args:
        filename: Path to the EVIO file
        start_event: First event to load
        end_event: Last event to load (exclusive)
        event_size_bytes: Size of each event in bytes (assumed fixed)

    Returns:
        NumPy array with shape (num_events, words_per_event)
    """
    print(f"Loading events {start_event}-{end_event-1} from {filename}")
    print(f"Assuming fixed event size of {event_size_bytes} bytes")

    # Calculate event size in 32-bit words
    event_size_words = event_size_bytes // 4
    print(f"Event size: {event_size_words} words")

    with EvioFile(filename) as evio_file:
        # Get first record for demonstration
        record = evio_file.get_record(2)

        # Get event offsets directly
        t0 = time.time()
        event_info = record.get_event_offsets(start_event, end_event)
        t1 = time.time()
        print(f"Got {len(event_info)} event offsets in {(t1-t0)*1000:.2f} ms")

        if not event_info:
            print("No events found in specified range")
            return None

        # Method 1: Use events_to_numpy_direct for loading into a 2D array
        t0 = time.time()
        events_data = record.events_to_numpy_direct(
            start_event=start_event,
            end_event=end_event,
            event_size_words=event_size_words
        )
        t1 = time.time()

        for row in events_data:
            hexs =" ".join([f"0x{word:08x}" for word in row])
            print(hexs)

        print(f"Loaded events using events_to_numpy_direct in {(t1-t0)*1000:.2f} ms")
        print(f"Result shape: {events_data.shape}")

        # Method 2: Direct memory mapping to NumPy
        t0 = time.time()

        # Calculate total size needed
        num_events = len(event_info)
        result = np.zeros((num_events, event_size_words), dtype=np.uint32)

        # Direct memory loading
        for i, (offset, _) in enumerate(event_info):
            # Using np.frombuffer for zero-copy access
            event_data = np.frombuffer(
                evio_file.mm[offset:offset + event_size_bytes],
                dtype=np.uint32
            )
            result[i, :len(event_data)] = event_data

        t1 = time.time()
        print(f"Loaded events using direct memory mapping in {(t1-t0)*1000:.2f} ms")
        print(f"Result shape: {result.shape}")

        # Compare first event data from both methods to verify
        if len(events_data) > 0 and len(result) > 0:
            print("\nVerifying first event data:")
            print(f"Method 1 first event: {events_data[0][:5]}...")
            print(f"Method 2 first event: {result[0][:5]}...")

            if np.array_equal(events_data[0], result[0]):
                print("✓ Events match!")
            else:
                print("✗ Events don't match!")

        # Analysis example: Check for specific signature in the second word
        signature = 0xFF60
        filtered_events = []

        for i, row in enumerate(result):
            hexs =" ".join([f"0x{word:08x}" for word in row])
            print(hexs)
            if len(row) >= 2 and (row[1] >> 16) == (signature & 0xFFFF):
                filtered_events.append(i)

        print(f"\nFound {len(filtered_events)} events with signature 0x{signature:04X}")

        if filtered_events:
            # Extract specific fields from matching events
            print("\nExtracted fields from first matching event:")
            event_idx = filtered_events[0]
            event_data = result[event_idx]

            # Example field extraction (customize based on actual data structure)
            header = event_data[0]
            tag_word = event_data[1]

            # Check if the event has timestamp fields
            if len(event_data) >= 4:
                timestamp_low = event_data[2]
                timestamp_high = event_data[3]
                timestamp = (int(timestamp_high) << 32) | int(timestamp_low)
                print(f"  Timestamp: {timestamp}")

            print(f"  Header: 0x{header:08X}")
            print(f"  Tag word: 0x{tag_word:08X}")

        return result


def benchmark_loading_methods(filename, num_iterations=5):
    """
    Benchmark different loading methods for comparison.
    """
    print(f"\nBenchmarking loading methods ({num_iterations} iterations each):")

    with EvioFile(filename) as evio_file:
        record = evio_file.get_record(0)

        # Method 1: Traditional get_events() with Event objects
        times = []
        for _ in range(num_iterations):
            t0 = time.time()
            events = record.get_events(0, 100)
            # Access some data to ensure loading
            for event in events:
                _ = event.offset
            t1 = time.time()
            times.append(t1 - t0)

        print(f"Traditional get_events(): {np.mean(times)*1000:.2f} ms ± {np.std(times)*1000:.2f} ms")

        # Method 2: Direct NumPy loading with fixed size
        times = []
        for _ in range(num_iterations):
            t0 = time.time()
            data = record.events_to_numpy_direct(0, 100, event_size_words=22)
            # Access data to ensure loading
            if len(data) > 0:
                _ = data[0][0]
            t1 = time.time()
            times.append(t1 - t0)

        print(f"events_to_numpy_direct(): {np.mean(times)*1000:.2f} ms ± {np.std(times)*1000:.2f} ms")

        # Method 3: Get offsets only
        times = []
        for _ in range(num_iterations):
            t0 = time.time()
            offsets = record.get_event_offsets(0, 100)
            t1 = time.time()
            times.append(t1 - t0)

        print(f"get_event_offsets(): {np.mean(times)*1000:.2f} ms ± {np.std(times)*1000:.2f} ms")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <evio_file> [start_event] [end_event] [event_size_bytes]")
        sys.exit(1)

    filename = sys.argv[1]

    # Parse optional arguments
    start_event = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    end_event = int(sys.argv[3]) if len(sys.argv) > 3 else start_event + 1001
    event_size_bytes = int(sys.argv[4]) if len(sys.argv) > 4 else 88

    if not os.path.exists(filename):
        print(f"Error: File {filename} not found")
        sys.exit(1)

    # Run the direct events loading example
    events_data = direct_events_loading2(filename, start_event, end_event, event_size_bytes)

    # Run benchmark
    # benchmark_loading_methods(filename)