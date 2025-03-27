import numpy as np
from pyevio import EvioFile

def extract_events_example(filename):
    """
    Example showing how to use the events_to_numpy method to efficiently
    extract events with FF60 signature and process them as a NumPy array.
    """
    print(f"Processing file: {filename}")

    # Open the EVIO file
    with EvioFile(filename) as evio_file:
        print(f"File contains {evio_file.record_count} records")

        # Process each record
        total_matching_events = 0
        total_extracted_words = 0

        for record_idx in range(evio_file.record_count):
            record = evio_file.get_record(record_idx)

            # Extract FF60 events to NumPy array
            data = record.events_to_numpy(signature=0xFF60)

            if len(data) > 0:
                total_matching_events += 1
                total_extracted_words += len(data)

                # Example analysis: Calculate statistics on the data
                data_mean = data.mean()
                data_min = data.min()
                data_max = data.max()

                print(f"Record {record_idx}: Extracted {len(data)} words")
                print(f"  Data statistics: Min={data_min}, Max={data_max}, Mean={data_mean:.2f}")

                # Example: Extract specific fields from the data
                # This would depend on the specific event structure
                if len(data) >= 10:  # Ensure we have enough data
                    # Extract example fields (customize based on actual data structure)
                    header = data[0]
                    tag_word = data[1]
                    timestamp_low = data[2] if len(data) > 2 else 0
                    timestamp_high = data[3] if len(data) > 3 else 0

                    # Combine timestamp parts (if using 64-bit timestamp)
                    timestamp = (timestamp_high << 32) | timestamp_low

                    print(f"  Header: 0x{header:08X}, Tag: 0x{tag_word:08X}")
                    print(f"  Timestamp: {timestamp}")

        print(f"Summary: Found matching events in {total_matching_events} records")
        print(f"Total extracted words: {total_extracted_words}")


def batch_process_example(filename, output_file=None):
    """
    Example showing how to batch process multiple records and combine results.

    Args:
        filename: Path to EVIO file
        output_file: Optional output file to save processed data
    """
    print(f"Batch processing file: {filename}")

    with EvioFile(filename) as evio_file:
        # Preallocate a list to store arrays from each record
        record_arrays = []

        # Process records in batches
        for record_idx in range(evio_file.record_count):
            record = evio_file.get_record(record_idx)

            # Extract FF60 events
            data = record.events_to_numpy(signature=0xFF60)

            if len(data) > 0:
                record_arrays.append(data)
                print(f"Record {record_idx}: Found {len(data)} words of matching data")

        # Combine all arrays (if any were found)
        if record_arrays:
            combined_data = np.concatenate(record_arrays)
            print(f"Combined data size: {len(combined_data)} words")

            # Example analysis on combined data
            if len(combined_data) > 0:
                print(f"Data statistics:")
                print(f"  Shape: {combined_data.shape}")
                print(f"  Min: {combined_data.min()}")
                print(f"  Max: {combined_data.max()}")
                print(f"  Mean: {combined_data.mean():.2f}")

                # Save to output file if requested
                if output_file:
                    np.save(output_file, combined_data)
                    print(f"Saved data to {output_file}")
        else:
            print("No matching events found in any record")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python example.py <evio_file> [output_file]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    # Run the example
    extract_events_example(input_file)
    print("\n" + "-" * 50 + "\n")
    batch_process_example(input_file, output_file)