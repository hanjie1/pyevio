import argparse
import struct
import numpy as np
from pyevio import EvioFile

# FADC250 Data Types
BLOCK_HEADER = 0
BLOCK_TRAILER = 1
EVENT_HEADER = 2
TRIGGER_TIME = 3
WINDOW_RAW_DATA = 4
WINDOW_SUM = 5
PULSE_RAW_DATA = 6
PULSE_INTEGRAL = 7
PULSE_TIME = 8
PULSE_DATA = 9
PULSE_PEDESTAL = 10
EVENT_TRAILER = 13
DATA_NOT_VALID = 14
FILLER_WORD = 15

def print_binary(word):
    """
    Format 32-bit word as binary string with spaces every 4 bits
    """
    binary = bin(word)[2:].zfill(32)
    return ' '.join(binary[i:i+4] for i in range(0, 32, 4))

def decode_fadc250_word(word):
    """
    Decode a FADC250 data continuation word (bit 31 = 0)

    Args:
        word: 32-bit data word to decode

    Returns:
        tuple: (channel, charge, time)
    """
    charge = word & 0x1FFF            # bits 0-12: Charge
    channel = (word >> 13) & 0x000F   # bits 13-16: Channel
    time = ((word >> 17) & 0x3FFF) * 4  # bits 17-30: Time (multiplied by 4)

    return (channel, charge, time)

def identify_fadc_word(word, current_data_type=None):
    """
    Identify the type and content of an FADC250 word

    Args:
        word: 32-bit data word to analyze
        current_data_type: Optional current data type context

    Returns:
        dict: Information about the word
    """
    result = {
        'word': word,
        'binary': print_binary(word),
        'is_type_defining': False,
        'data_type': None,
        'data_type_name': "Unknown",
        'description': ""
    }

    # Check if this is a type-defining word (bit 31 = 1)
    if ((word >> 31) & 0x1) == 1:
        result['is_type_defining'] = True
        data_type = (word >> 27) & 0xF
        result['data_type'] = data_type

        data_type_names = {
            0: "Block Header",
            1: "Block Trailer",
            2: "Event Header",
            3: "Trigger Time",
            4: "Window Raw Data",
            5: "Window Sum",
            6: "Pulse Raw Data",
            7: "Pulse Integral",
            8: "Pulse Time",
            9: "Pulse Data",
            10: "Pulse Pedestal",
            13: "Event Trailer",
            14: "Data Not Valid",
            15: "Filler Word"
        }

        result['data_type_name'] = data_type_names.get(data_type, f"Unknown ({data_type})")

        # Extract additional fields based on data type
        if data_type == BLOCK_HEADER:
            slot = (word >> 22) & 0x1F
            event_count = (word >> 14) & 0xFF
            module_type = (word >> 12) & 0x3
            block_num = word & 0xFFF
            result['description'] = f"Slot {slot}, Events {event_count}, Module {module_type}, Block {block_num}"
            result['slot'] = slot

        elif data_type == BLOCK_TRAILER:
            slot = (word >> 22) & 0x1F
            word_count = word & 0x3FFFFF
            result['description'] = f"Slot {slot}, Words {word_count}"
            result['slot'] = slot

        elif data_type == EVENT_HEADER:
            slot = (word >> 22) & 0x1F
            module_type = (word >> 20) & 0x3
            trigger_num = word & 0x3FFFFF
            result['description'] = f"Slot {slot}, Module {module_type}, Trigger {trigger_num}"
            result['slot'] = slot
            result['trigger_num'] = trigger_num

        elif data_type == WINDOW_RAW_DATA:
            channel = (word >> 23) & 0x0F
            window_width = word & 0x0FFF
            result['description'] = f"Channel {channel}, Width {window_width}"
            result['channel'] = channel
            result['window_width'] = window_width

        elif data_type == WINDOW_SUM:
            channel = (word >> 23) & 0x0F
            sum_value = word & 0x3FFFFF
            overflow = (word >> 22) & 0x1
            result['description'] = f"Channel {channel}, Sum {sum_value}, Overflow {overflow}"

        elif data_type == PULSE_INTEGRAL:
            channel = (word >> 23) & 0x0F
            pulse_number = (word >> 21) & 0x03
            quality_factor = (word >> 19) & 0x03
            sum_value = word & 0x7FFFF
            result['description'] = f"Channel {channel}, Pulse# {pulse_number}, QF {quality_factor}, Sum {sum_value}"

        elif data_type == PULSE_TIME:
            channel = (word >> 23) & 0x0F
            pulse_number = (word >> 21) & 0x03
            quality_factor = (word >> 19) & 0x03
            pulse_time = word & 0x7FFFF
            result['description'] = f"Channel {channel}, Pulse# {pulse_number}, QF {quality_factor}, Time {pulse_time}"

        elif data_type == PULSE_DATA:
            event_number_within_block = (word >> 19) & 0xFF
            channel = (word >> 15) & 0x0F
            QF_pedestal = (word >> 14) & 0x01
            pedestal = word & 0x3FFF
            result['description'] = f"Channel {channel}, Pedestal {pedestal}, Event# {event_number_within_block}"

    else:
        # This is a data continuation word
        result['is_type_defining'] = False

        # Decode based on context of current data type if provided
        if current_data_type in [WINDOW_RAW_DATA, PULSE_RAW_DATA, PULSE_INTEGRAL, PULSE_TIME]:
            channel, charge, time = decode_fadc250_word(word)
            result['description'] = f"Channel {channel}, Charge {charge}, Time {time}"
            result['channel'] = channel
            result['charge'] = charge
            result['time'] = time
        elif current_data_type == PULSE_DATA:
            # Check the format code in bits 30-29
            format_code = (word >> 29) & 0x3
            if format_code == 1:  # Word2 format
                integral = (word >> 12) & 0x3FFFF
                QF_NSA_beyond_PTW = (word >> 11) & 0x01
                QF_overflow = (word >> 10) & 0x01
                QF_underflow = (word >> 9) & 0x01
                nsamples_over_threshold = word & 0x1FF
                result['description'] = f"Integral {integral}, Samples over threshold {nsamples_over_threshold}"
            elif format_code == 0:  # Word3 format
                course_time = (word >> 21) & 0x1FF
                fine_time = (word >> 15) & 0x3F
                pulse_peak = (word >> 3) & 0xFFF
                result['description'] = f"Time {course_time}, Fine {fine_time}, Peak {pulse_peak}"
        else:
            # Generic decoding for data continuation
            channel, charge, time = decode_fadc250_word(word)
            result['description'] = f"Data continuation word: Channel {channel}, Charge {charge}, Time {time}"

    return result

def analyze_evio_data(filename, max_events=None, verbose=True):
    """
    Parse EVIO file and analyze FADC250 data with detailed debugging
    """
    print(f"Processing file: {filename}")

    # Open the EVIO file
    with EvioFile(filename) as evio_file:
        print(f"File contains {evio_file.record_count} records")

        global_evt_index = 0

        for record_idx in range(evio_file.record_count):
            record = evio_file.get_record(record_idx)
            events = record.get_events()

            for event_idx, event in enumerate(events):
                try:
                    # Limit events if requested
                    if max_events is not None and global_evt_index >= max_events:
                        return

                    # Get the top-level bank
                    root_bank = event.get_bank()

                    # Skip non-physics events
                    if root_bank.tag != 0xFF50:
                        global_evt_index += 1
                        continue

                    print(f"\nEvent {global_evt_index}, Record {record_idx}, Event {event_idx}")
                    print(f"  Physics Event (0x{root_bank.tag:04X}, type: 0x{root_bank.data_type:02X})")

                    # Find EB Bank (0x0001)
                    eb_bank = None
                    for child in root_bank.get_children():
                        if child.tag == 0x0001:
                            eb_bank = child
                            print(f"  EB Bank (0x{child.tag:04X}) - Size: {child.length} words")
                            break

                    if not eb_bank:
                        print("  No EB Bank found")
                        global_evt_index += 1
                        continue

                    # Find ROC data (typically 0x0003)
                    for data_child in eb_bank.get_children():
                        roc_id = data_child.tag
                        print(f"    ROC {roc_id} (0x{data_child.tag:04X}) - Size: {data_child.length} words")

                        # Get raw data for ROC
                        raw_data = data_child.to_numpy()
                        if raw_data is None or len(raw_data) == 0:
                            print("      No data found")
                            continue

                        # Analyze the data words with detailed debugging
                        print(f"      Detailed Word Analysis (showing all {len(raw_data)} words):")
                        print("      -----------------------------------------")
                        print("      Word#  Hex Value   Type Defining  Type            Description")
                        print("      -----------------------------------------")

                        current_data_type = None
                        current_slot = None

                        for i, word in enumerate(raw_data):
                            # Identify and decode the word
                            word_info = identify_fadc_word(word, current_data_type)

                            # Update context for next words
                            if word_info['is_type_defining']:
                                current_data_type = word_info['data_type']
                                if 'slot' in word_info:
                                    current_slot = word_info['slot']

                            # Print detailed info
                            type_str = "Yes" if word_info['is_type_defining'] else "No"
                            print(f"      {i:5d}  0x{word:08X}  {type_str:12}  {word_info['data_type_name']:<15} {word_info['description']}")

                            # Show binary representation for more debugging
                            if verbose:
                                print(f"              Binary: {word_info['binary']}")

                        print("      -----------------------------------------")

                        # Perform a second pass to match up data - follow the C++ code logic
                        print("      FADC250 Data Summary:")
                        parser_context = {
                            'slot': None,
                            'trigger': None,
                            'data_type': None,
                            'channel': None,
                            'window_width': None
                        }

                        i = 0
                        while i < len(raw_data):
                            word = raw_data[i]

                            # Skip data continuation words at this level
                            if ((word >> 31) & 0x1) == 0:
                                i += 1
                                continue

                            # Process type-defining words
                            data_type = (word >> 27) & 0xF

                            if data_type == BLOCK_HEADER:
                                slot = (word >> 22) & 0x1F
                                parser_context['slot'] = slot
                                print(f"      Block Header: Slot {slot}")

                            elif data_type == EVENT_HEADER:
                                slot = (word >> 22) & 0x1F
                                trigger = word & 0x3FFFFF
                                parser_context['slot'] = slot
                                parser_context['trigger'] = trigger
                                print(f"      Event Header: Slot {slot}, Trigger {trigger}")

                            elif data_type == WINDOW_RAW_DATA:
                                # Window Raw Data extraction
                                channel = (word >> 23) & 0x0F
                                window_width = word & 0x0FFF
                                parser_context['channel'] = channel
                                parser_context['window_width'] = window_width

                                samples = []
                                j = i + 1
                                while j < len(raw_data) and ((raw_data[j] >> 31) & 0x1) == 0:
                                    next_word = raw_data[j]
                                    # Process samples according to the C++ code
                                    invalid_1 = (next_word >> 29) & 0x1
                                    invalid_2 = (next_word >> 13) & 0x1
                                    sample_1 = (next_word >> 16) & 0x1FFF if not invalid_1 else 0
                                    sample_2 = (next_word >> 0) & 0x1FFF if not invalid_2 else 0
                                    samples.append(sample_1)
                                    samples.append(sample_2)
                                    j += 1

                                print(f"      Window Raw Data: Slot {parser_context['slot']}, Channel {channel}, Width {window_width}, Samples: {len(samples)}")
                                # Skip to the last continuation word
                                i = j - 1

                            elif data_type == PULSE_INTEGRAL:
                                channel = (word >> 23) & 0x0F
                                pulse_number = (word >> 21) & 0x03
                                quality_factor = (word >> 19) & 0x03
                                integral = word & 0x7FFFF
                                print(f"      Pulse Integral: Slot {parser_context['slot']}, Channel {channel}, Pulse# {pulse_number}, QF {quality_factor}, Sum {integral}")

                            elif data_type == PULSE_TIME:
                                channel = (word >> 23) & 0x0F
                                pulse_number = (word >> 21) & 0x03
                                quality_factor = (word >> 19) & 0x03
                                pulse_time = word & 0x7FFFF
                                print(f"      Pulse Time: Slot {parser_context['slot']}, Channel {channel}, Pulse# {pulse_number}, QF {quality_factor}, Time {pulse_time}")

                            # Move to next word
                            i += 1

                except Exception as e:
                    print(f"  Error processing event {global_evt_index}: {str(e)}")

                global_evt_index += 1

                # Limit events if requested
                if max_events is not None and global_evt_index >= max_events:
                    return

if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description="Experiments with evio FADC250 data")
    parser.add_argument("input_files", nargs="+", help="One or more EVIO files to process.")
    parser.add_argument("-e", "--events", type=int, default=None, help="If set, stop processing after this many events.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output.")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory where output plots will be saved.")
    args = parser.parse_args()

    # Run the example
    analyze_evio_data(args.input_files[0], args.events, args.verbose)
    print("\n" + "-" * 50 + "\n")