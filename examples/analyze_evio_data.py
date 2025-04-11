import argparse
import struct

import numpy as np
from pyevio import EvioFile

def decode_fadc_word(frame_time_ns, payload_id, word):
    """
    Decode a single FADC250 data word.

    Args:
        frame_time_ns: Frame timestamp in nanoseconds
        payload_id: Payload ID
        word: 32-bit data word to decode

    Returns:
        tuple: (payload_id, channel, q, ht)
    """
    q = word & 0x1FFF  # 13 least significant bits
    channel = (word >> 13) & 0x000F  # 4 bits starting from bit 13
    v = ((word >> 17) & 0x3FFF) * 4  # 14 bits starting from bit 17, multiplied by 4
    ht = frame_time_ns + v  # Hit time

    return (payload_id, channel, q, ht)

def decode_fadc_word2(frame_time_ns, payload_id, word):
    """
    Decode a single FADC250 data word.

    Args:
        frame_time_ns: Frame timestamp in nanoseconds
        payload_id: Payload ID
        word: 32-bit data word to decode

    Returns:
        tuple: (payload_id, channel, q, ht)
    """
    # Match exactly the Java implementation
    q = word & 0x1FFF                      # Bits 0-12
    channel = (word >> 13) & 0x000F        # Bits 13-16
    v = ((word >> 17) & 0x3FFF) * 4        # Bits 17-30, multiplied by 4
    ht = frame_time_ns + v

    return (payload_id, channel, q, ht)

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
                if evt_len > 88:
                    # Get the last word from the event data
                    last_word_offset = evt_offset + evt_len - 4
                    last_word = struct.unpack(record.endian + 'I',
                                              record.mm[last_word_offset:last_word_offset + 4])[0]

                    # Use placeholder values for now - in a real application,
                    # you'd extract these from the event/record context
                    frame_time_ns = 0
                    payload_id = global_evt_index

                    # Decode the word
                    decoded_payload_id, channel, q, ht = decode_fadc_word(frame_time_ns, payload_id, last_word)

                    print(f"1 Event {global_evt_index}, Record {record_idx}, Event {i}:")
                    print(f"1   Offset: {evt_offset}, Length: {evt_len}")
                    print(f"1   Last Word Decoded: PayloadID={decoded_payload_id}, Channel={channel}, Q={q}, HT={ht}")

                    decoded_payload_id, channel, q, ht = decode_fadc_word2(frame_time_ns, payload_id, last_word)

                    print(f"2 Event {global_evt_index}, Record {record_idx}, Event {i}:")
                    print(f"2   Offset: {evt_offset}, Length: {evt_len}")
                    print(f"2   Last Word Decoded: PayloadID={decoded_payload_id}, Channel={channel}, Q={q}, HT={ht}")



                global_evt_index += 1

        print(f"Summary: Found matching events in {total_matching_events} records")
        print(f"Total extracted words: {total_extracted_words}")

if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description="Experiments with evio FADC250 data")
    parser.add_argument("input_files", nargs="+", help="One or more EDM4eic ROOT files to process.")
    parser.add_argument("-e", "--events", type=int, default=None,
                        help="If set, stop processing after this many events (across all files).")
    parser.add_argument("-o", "--output-dir", default="output",
                        help="Directory where output plots will be saved.")
    args = parser.parse_args()

    # Run the example
    extract_events_example(args.input_files[0])
    print("\n" + "-" * 50 + "\n")