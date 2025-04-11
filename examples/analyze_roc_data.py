import argparse
import struct
import numpy as np
from pyevio import EvioFile

# Known special patterns
END_MARKER = 0x0000C0F8
PEDESTAL_MARKER = 0x0600C088

def decode_fadc250_data(word):
    """
    Decode a FADC250 data word according to the JLab documentation.

    Args:
        word: 32-bit word to decode

    Returns:
        dict: Decoded information
    """
    # Check if this is a type-defining word
    is_type_word = ((word >> 31) & 0x1) == 1

    if is_type_word:
        # Get data type from bits 30-27
        data_type = (word >> 27) & 0xF

        type_info = {
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

        result = {
            'is_type_word': True,
            'data_type': data_type,
            'type_name': type_info.get(data_type, f"Unknown ({data_type})"),
            'word': word
        }

        # Extract fields based on type
        if data_type == 0:  # Block Header
            result['slot'] = (word >> 22) & 0x1F
            result['event_count'] = (word >> 14) & 0xFF
            result['module_type'] = (word >> 12) & 0x3
            result['block_num'] = word & 0xFFF

        elif data_type == 1:  # Block Trailer
            result['slot'] = (word >> 22) & 0x1F
            result['word_count'] = word & 0x3FFFFF

        elif data_type == 2:  # Event Header
            result['slot'] = (word >> 22) & 0x1F
            result['module_type'] = (word >> 20) & 0x3
            result['trigger_num'] = word & 0x3FFFFF

        elif data_type == 3:  # Trigger Time
            result['time_low'] = word & 0xFFFFFF

        elif data_type == 4:  # Window Raw Data
            result['channel'] = (word >> 23) & 0x0F
            result['window_width'] = word & 0x0FFF

        elif data_type == 5:  # Window Sum
            result['channel'] = (word >> 23) & 0x0F
            result['overflow'] = (word >> 22) & 0x1
            result['sum'] = word & 0x3FFFFF

        elif data_type == 7:  # Pulse Integral
            result['channel'] = (word >> 23) & 0x0F
            result['pulse_number'] = (word >> 21) & 0x03
            result['quality_factor'] = (word >> 19) & 0x03
            result['sum'] = word & 0x7FFFF

        elif data_type == 8:  # Pulse Time
            result['channel'] = (word >> 23) & 0x0F
            result['pulse_number'] = (word >> 21) & 0x03
            result['quality_factor'] = (word >> 19) & 0x03
            result['time'] = word & 0x7FFFF

        return result

    else:
        # This is a data word - decode according to FADC250 format
        channel = (word >> 13) & 0x000F
        charge = word & 0x1FFF
        time = ((word >> 17) & 0x3FFF) * 4

        # Check for known special patterns
        is_end_marker = (word == END_MARKER)
        is_pedestal_marker = (word == PEDESTAL_MARKER)

        type_name = "Data"
        if is_end_marker:
            type_name = "End Marker"
        elif is_pedestal_marker:
            type_name = "Pedestal Marker"

        return {
            'is_type_word': False,
            'is_special_marker': is_end_marker or is_pedestal_marker,
            'type_name': type_name,
            'channel': channel,
            'charge': charge,
            'time': time,
            'word': word
        }

def analyze_fadc250_event(event, verbose=False):
    """
    Analyze an EVIO event for FADC250 data.

    Args:
        event: EVIO event object
        verbose: Whether to print detailed output

    Returns:
        dict: Decoded FADC250 data
    """
    try:
        # Get the root bank for this event
        root_bank = event.get_bank()

        # Only process physics events (0xFF50)
        if root_bank.tag != 0xFF50:
            return None

        result = {
            'physics_event': True,
            'roc_data': {}
        }

        # Find Event Builder bank (0x0001)
        eb_bank = None
        for child in root_bank.get_children():
            if child.tag == 0x0001:
                eb_bank = child
                break

        if not eb_bank:
            return result

        # Process ROC data banks
        for roc_bank in eb_bank.get_children():
            roc_id = roc_bank.tag
            if roc_id not in result['roc_data']:
                result['roc_data'][roc_id] = {
                    'raw_words': [],
                    'decoded_words': [],
                    'hits': []
                }

            # Get raw data words
            raw_data = roc_bank.to_numpy()
            if raw_data is None or len(raw_data) == 0:
                continue

            # Store raw words
            result['roc_data'][roc_id]['raw_words'] = raw_data.tolist()

            # Decode all words
            for word in raw_data:
                decoded = decode_fadc250_data(word)
                result['roc_data'][roc_id]['decoded_words'].append(decoded)

                # Extract hit information from data words, excluding special markers
                if not decoded['is_type_word'] and not decoded.get('is_special_marker', False):
                    result['roc_data'][roc_id]['hits'].append({
                        'channel': decoded['channel'],
                        'charge': decoded['charge'],
                        'time': decoded['time']
                    })

        return result

    except Exception as e:
        if verbose:
            print(f"Error analyzing event: {str(e)}")
        return None

def extract_events_example(filename, max_events=None, verbose=False):
    """
    Process EVIO file and extract FADC250 data.
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
                # Limit events if requested
                if max_events is not None and global_evt_index >= max_events:
                    return

                # Analyze the event
                event_data = analyze_fadc250_event(event, verbose)

                if event_data:
                    print(f"\nEvent {global_evt_index}, Record {record_idx}, Event {event_idx}")

                    # Process each ROC
                    for roc_id, roc_data in event_data['roc_data'].items():
                        print(f"  ROC {roc_id} (0x{roc_id:04X}): {len(roc_data['raw_words'])} words")

                        # Display detailed word analysis
                        if verbose:
                            print("  Word Analysis:")
                            print("  ---------------------------------------------")
                            print("  Word#  Hex Value   Type      Description")
                            print("  ---------------------------------------------")

                            for i, (word, decoded) in enumerate(zip(roc_data['raw_words'], roc_data['decoded_words'])):
                                binary = bin(word)[2:].zfill(32)
                                bit31 = binary[0]

                                if decoded['is_type_word']:
                                    type_name = decoded['type_name']

                                    # Format description based on type
                                    if 'slot' in decoded:
                                        if 'trigger_num' in decoded:
                                            desc = f"Slot {decoded['slot']}, Trigger {decoded['trigger_num']}"
                                        else:
                                            desc = f"Slot {decoded['slot']}"
                                    elif 'channel' in decoded:
                                        if 'sum' in decoded:
                                            desc = f"Channel {decoded['channel']}, Sum {decoded['sum']}"
                                        elif 'time' in decoded:
                                            desc = f"Channel {decoded['channel']}, Time {decoded['time']}"
                                        else:
                                            desc = f"Channel {decoded['channel']}"
                                    else:
                                        desc = ""

                                elif decoded.get('is_special_marker', False):
                                    type_name = decoded['type_name']
                                    if type_name == "End Marker":
                                        desc = "(Data stream end marker)"
                                    elif type_name == "Pedestal Marker":
                                        desc = "(Pedestal/calibration reference)"
                                    else:
                                        desc = "(Not an actual hit)"
                                else:
                                    type_name = "Data"
                                    desc = f"Channel {decoded['channel']}, Charge {decoded['charge']}, Time {decoded['time']}"

                                print(f"  {i:5d}  0x{word:08X}  {type_name:<10}  {desc}")
                                print(f"          Bit31={bit31}, Binary: {' '.join(binary[i:i+4] for i in range(0, 32, 4))}")

                        # Show hits summary, excluding special markers
                        if roc_data['hits']:
                            print(f"  Found {len(roc_data['hits'])} real hits:")
                            for i, hit in enumerate(roc_data['hits'][:5]):  # Show first 5 hits
                                print(f"    Hit {i}: Channel {hit['channel']}, Charge {hit['charge']}, Time {hit['time']}")

                            if len(roc_data['hits']) > 5:
                                print(f"    ... and {len(roc_data['hits'])-5} more hits")

                global_evt_index += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Experiments with evio FADC250 data")
    parser.add_argument("input_files", nargs="+", help="One or more EVIO files to process.")
    parser.add_argument("-e", "--events", type=int, default=None, help="If set, stop processing after this many events.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output.")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory where output plots will be saved.")
    args = parser.parse_args()

    # Run the example
    extract_events_example(args.input_files[0], args.events, args.verbose)
    print("\n" + "-" * 50 + "\n")