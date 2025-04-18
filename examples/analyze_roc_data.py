import argparse
import struct
import numpy as np
from pyevio import EvioFile, Bank
from rich import inspect as rich_inspect

from pyevio.decoders.fadc250_triggered import FaDecoder


# --- new helper --------------------------------------------------------------
def _payload_to_words(data: bytes, little_endian: bool) -> np.ndarray:
    """
    View a raw bytes object as an array of 32‑bit unsigned words.

    Args:
        data          : raw payload returned by Bank.get_data()
        little_endian : True  -> '<u4'
                        False -> '>u4'

    Returns
    -------
        np.ndarray of dtype uint32, 1‑D.
    """
    # NB: EVIO banks are always word‑aligned.  If something is off,
    # raise early – it usually means the bank is corrupt or the caller
    # sliced too far.
    if len(data) % 4:
        raise ValueError(f"payload length {len(data)} is not a multiple of 4 bytes")

    dtype = np.dtype('<u4' if little_endian else '>u4')
    return np.frombuffer(data, dtype=dtype)
# -----------------------------------------------------------------------------


def analyze_data_bank(bank: Bank, verbose: bool = False, decoder  = None):
    """
    Decode a *single* ROC‑data bank that contains raw FADC‑250 words.

    Parameters
    ----------
    bank     : Bank
        The EVIO bank whose payload should be decoded.
    verbose  : bool, optional
        Forwarded to FaDecoder.faDataDecode().
    decoder  : FaDecoder | None, optional
        If supplied, the same decoder instance will be reused; otherwise
        a fresh one is created.

    Returns
    -------
    dict
        Snapshot of the decoder’s state after the last word – useful if
        you want to inspect integrals, times, hit counts, etc.
    """
    # ---------- 1. pick a decoder -------------------------------------------
    dec = decoder or FaDecoder()

    # ---------- 2. get payload as uint32 words ------------------------------
    payload = bank.get_data()
    words   = _payload_to_words(payload, little_endian=(bank.endian == '<'))

    # ---------- 3. loop over words ------------------------------------------
    for w in words:
        # convert NumPy scalar to plain Python int for clarity
        dec.faDataDecode(int(w), verbose=verbose)

    rich_inspect(dec.fadc_data, methods=False, private=False)

    # ---------- 4. return whatever you need ---------------------------------
    # Here we simply expose the internal struct so the caller can grab
    # integrals, times, scaler counts, etc.  Tailor to taste.
    return {
        "slot"       : dec.fadc_data.slot_id_hd,
        "trig_time"  : getattr(dec, "fadc_trigtime", None),
        "nhit"       : dec.fadc_nhit.copy(),
        "integrals"  : dec.fadc_int.copy(),
        "times"      : dec.fadc_time.copy(),
        # ... add anything else you want to keep
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

    # Get the root bank for this event
    root_bank = event.get_bank()

    # Only process physics events (0xFF50)
    if root_bank.tag != 0xFF50:
        return None

    result = {
        'physics_event': True,
        'roc_data': {}
    }

    children = list(root_bank.get_children())
    print(f"len(children) = {len(children)}")

    if len(children) < 2:
        print(f"len(children) < 2")
        return None

    if children[0].tag == 0xFF21:
        print("Found FF21 bank")
    else:
        print(f"Unknown bank {children[0].tag:2X} bank")
        return None

    for i in range(1, len(children)):
        analyze_data_bank(children[i], verbose)


def extract_events_example(filename, max_event=10, verbose=False):
    """
    Process EVIO file and extract FADC250 data.
    """
    print(f"Processing file: {filename}")

    # Open the EVIO file
    with EvioFile(filename) as evio_file:
        print(f"File contains {evio_file.record_count} records")

        total_event_count = evio_file.get_total_event_count()
        print(f"File total_event_count = {total_event_count}")
        if max_event is None:
            max_event = total_event_count
        else:
            max_event = min(max_event, total_event_count)
        print(f"max_event is set to: {max_event}")

        global_evt_index = 0
        event_iter = evio_file.iter_events()

        for record, event in evio_file.iter_events():
            if global_evt_index >= max_event:
                break
            global_evt_index += 1

            # First two events are control and we skip them
            if global_evt_index < 2:
                continue

            event_data = analyze_fadc250_event(event, verbose)




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