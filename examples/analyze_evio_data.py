import argparse

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
        global_evt_index = 0

        for record_idx in range(evio_file.record_count):
            record = evio_file.get_record(record_idx)

            # Get event offsets and lengths
            event_infos = record.get_event_offsets()


            for i, (evt_offset, evt_len) in enumerate(event_infos):
                global_evt_index += 1
                if len > 92:
                    print(global_evt_index, i, record_idx, evt_offset, evt_len)
                    exit(0)


        print(f"Summary: Found matching events in {total_matching_events} records")
        print(f"Total extracted words: {total_extracted_words}")


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description="Experiments with evio FADC250 data")
    parser.add_argument("input_files", nargs="+", help="One or more EDM4eic ROOT files to process.")
    parser.add_argument("-e", "--events", type=int, default=None, help="If set, stop processing after this many events (across all files).")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory where output plots will be saved.")
    args = parser.parse_args()

    # Run the example
    extract_events_example(args.input_files[0])
    print("\n" + "-" * 50 + "\n")
