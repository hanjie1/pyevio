# This file decodes FADC bank for payload
# Originates from C++ code:
#    https://github.com/hanjie1/STONE/blob/main/Fadc250Decode.h
#
import argparse
import struct
import numpy as np
from pyevio import EvioFile, Bank
from rich import inspect as rich_inspect

# Known special patterns
END_MARKER = 0x0000C0F8
PEDESTAL_MARKER = 0x0600C088


class FadcDataStruct:
    """
    Replicates the fields of the C++ struct fadc_data_struct
    """
    def __init__(self):
        self.new_type       = 0
        self.type           = 0
        self.slot_id_hd     = 0
        self.slot_id_tr     = 0
        self.slot_id_evt    = 0
        self.n_evts         = 0
        self.blk_num        = 0
        self.n_words        = 0
        self.evt_num_1      = 0
        self.evt_num_2      = 0
        self.time_now       = 0
        self.time_1         = 0
        self.time_2         = 0
        self.chan           = 0
        self.width          = 0
        self.valid_1        = 0
        self.adc_1          = 0
        self.valid_2        = 0
        self.adc_2          = 0
        self.over           = 0
        self.adc_sum        = 0
        self.pulse_num      = 0
        self.thres_bin      = 0
        self.quality        = 0
        self.integral       = 0
        self.time           = 0
        self.chan_a         = 0
        self.source_a       = 0
        self.chan_b         = 0
        self.source_b       = 0
        self.group          = 0
        self.time_coarse    = 0
        self.time_fine      = 0
        self.vmin           = 0
        self.vpeak          = 0
        self.trig_type_int  = 0
        self.trig_state_int = 0
        self.evt_num_int    = 0
        self.err_status_int = 0
        self.num_scaler     = 0


class FaDecoder:
    """
    A class to hold state variables and decode an unsigned 32-bit word
    in the same manner as the original C++ code.

    Usage:
        dec = FaDecoder()
        dec.faDataDecode(data_word, verbose=True)
    """
    def __init__(self):
        # replicate "static" variables from the C++ code
        self.fadc_data            = FadcDataStruct()
        self.type_last            = 15   # Initialize to filler word
        self.time_last            = 0
        self.iword                = 0

        # replicate global variables
        self.data_type_4 = 0
        self.data_type_6 = 0
        self.data_type_7 = 0
        self.data_type_8 = 0

        self.nsamples   = 0
        self.trignum    = 0
        self.nrawdata   = 0
        self.mychan     = 0
        self.ftdc_nhit  = [0]*16
        self.oldchan    = -1
        self.nscalwrd   = 0

        # You have references to arrays like:
        #   fadc_nhit, ftdc_nhit, frawdata, fadc_int, fadc_time, ...
        # We don't have full definitions for these in the snippet; define or stub them:
        self.FADC_NCHAN   = 16    # from context
        self.MAXRAW       = 4096  # guess or read from context
        self.MAXHIT       = 10
        self.fadc_nhit    = [0]*self.FADC_NCHAN
        self.frawdata     = [ [0]*self.MAXRAW for _ in range(self.FADC_NCHAN) ]
        self.fadc_int     = [0]*self.FADC_NCHAN
        self.fadc_int_1   = [0]*self.FADC_NCHAN
        self.fadc_time    = [0]*self.FADC_NCHAN
        self.fadc_time_1  = [0]*self.FADC_NCHAN

        # For scaler storage
        self.fadc_scal_cnt    = [0]*16
        self.fadc_scal_time   = 0
        self.fadc_scal_trigcnt= 0
        self.fadc_scal_update = 0

        # We'll store fadc_trigtime as an attribute as well
        self.fadc_trigtime = 0


    def GetFadcMode(self):
        """
        Replicates the C++ code:
            if data_type_4 and not data_type_6 and not data_type_7 and not data_type_8 -> mode=1
            elif ...
        """
        mode = -1
        if (self.data_type_4 and not self.data_type_6 and not self.data_type_7 and not self.data_type_8):
            mode = 1
        elif (not self.data_type_4 and self.data_type_6 and not self.data_type_7 and not self.data_type_8):
            mode = 2
        elif (not self.data_type_4 and not self.data_type_6 and self.data_type_7 and self.data_type_8):
            mode = 3
        return mode


    def faDataDecode(self, data: int, verbose: bool=False):
        """
        Decodes a single 32-bit data word.
        :param data:    32-bit unsigned integer
        :param verbose: If True, print debug info
        """
        # We'll store a reference for shorter use:
        fadc_data = self.fadc_data

        # "static unsigned int type_last" is stored in self.type_last
        # "static unsigned int time_last" is stored in self.time_last
        # "static unsigned int iword" is stored in self.iword

        if verbose:
            print(f"{self.iword:3d}:", end=" ")
        self.iword += 1

        # data & 0x80000000 => if set, new data type
        if data & 0x80000000:
            fadc_data.new_type = 1
            fadc_data.type = (data & 0x78000000) >> 27
        else:
            fadc_data.new_type = 0
            fadc_data.type = self.type_last

        # Switch on fadc_data.type
        t = fadc_data.type

        if t == 0:  # BLOCK HEADER
            if fadc_data.new_type:
                fadc_data.slot_id_hd = (data & 0x7C00000) >> 22
                fadc_data.blk_num    = (data >> 8) & 0x3FF
                fadc_data.n_evts     = data & 0xFF
                if verbose:
                    print(f"{data:08X} - BLOCK HEADER - slot = {fadc_data.slot_id_hd}   "
                          f"n_evts = {fadc_data.n_evts}   n_blk = {fadc_data.blk_num}")

        elif t == 1:  # BLOCK TRAILER
            fadc_data.slot_id_tr = (data & 0x7C00000) >> 22
            fadc_data.n_words    = (data & 0x3FFFFF)
            if verbose:
                print(f"{data:08X} - BLOCK TRAILER - slot = {fadc_data.slot_id_tr}   "
                      f"n_words = {fadc_data.n_words}")

        elif t == 2:  # EVENT HEADER
            if fadc_data.new_type:
                fadc_data.slot_id_evt = (data >> 22) & 0x1F
                if fadc_data.slot_id_evt != fadc_data.slot_id_hd and verbose:
                    print("FADC Warning: event slot id is not the same as the block slot id !")

                fadc_data.evt_num_1 = data & 0x3FFFFF
                self.trignum        = fadc_data.evt_num_1
                if verbose:
                    print(f"{data:08X} - EVENT HEADER 1 - evt_num = {fadc_data.evt_num_1}")
            else:
                fadc_data.evt_num_2 = data & 0x3FFFFF
                if verbose:
                    print(f"{data:08X} - EVENT HEADER 2 - evt_num = {fadc_data.evt_num_2}")

        elif t == 3:  # TRIGGER TIME
            if fadc_data.new_type:
                fadc_data.time_1 = data & 0xFFFFFF
                if verbose:
                    print(f"{data:08X} - TRIGGER TIME 1 - time = {fadc_data.time_1:08x}")
                fadc_data.time_now = 1
                self.time_last     = 1
            else:
                if self.time_last == 1:
                    fadc_data.time_2 = data & 0xFFFFFF
                    if verbose:
                        print(f"{data:08X} - TRIGGER TIME 2 - time = {fadc_data.time_2:08x}")
                    fadc_data.time_now = 2

                    # The original code sets fadc_trigtime
                    self.fadc_trigtime = ((fadc_data.time_2 << 24) | fadc_data.time_1)
                else:
                    if verbose:
                        print("FADC Warning: trigger time is more than 2 words!!")

        elif t == 4:  # WINDOW RAW DATA
            if fadc_data.new_type:
                self.data_type_4 = 1
                fadc_data.chan  = (data & 0x07800000) >> 23
                fadc_data.width = (data & 0xFFF)
                self.nsamples   = fadc_data.width

                if fadc_data.chan != self.oldchan:
                    self.nrawdata = 0
                    self.oldchan  = fadc_data.chan

                if fadc_data.chan < self.FADC_NCHAN:
                    self.fadc_nhit[fadc_data.chan] += 1
                else:
                    print(f"FADC: Something wrong here! chan {fadc_data.chan+1} > FADC_NCHAN ({self.FADC_NCHAN})")

                if verbose:
                    print(f"{data:08X} - WINDOW RAW DATA - chan = {fadc_data.chan}   "
                          f"nsamples = {fadc_data.width}")
            else:
                fadc_data.valid_1 = 1
                fadc_data.valid_2 = 1
                fadc_data.adc_1   = (data & 0x1FFF0000) >> 16
                if data & 0x20000000:
                    fadc_data.valid_1 = 0
                fadc_data.adc_2   = (data & 0x1FFF)
                if data & 0x2000:
                    fadc_data.valid_2 = 0

                if verbose:
                    print(f"{data:08X} - RAW SAMPLES - valid = {fadc_data.valid_1}  chan = {fadc_data.chan} "
                          f"adc = {fadc_data.adc_1:4d}   valid = {fadc_data.valid_2}  adc = {fadc_data.adc_2:4d}")

                if (self.nrawdata < self.MAXRAW) and (fadc_data.chan < self.FADC_NCHAN):
                    self.frawdata[fadc_data.chan][self.nrawdata] = fadc_data.adc_1
                    self.nrawdata += 1
                    self.frawdata[fadc_data.chan][self.nrawdata] = fadc_data.adc_2
                    self.nrawdata += 1
                else:
                    if self.nrawdata > self.MAXRAW:
                        print("Warning: Decode:  too many raw data words ?")

        elif t == 5:  # WINDOW SUM
            fadc_data.over = 0
            fadc_data.chan = (data & 0x07800000) >> 23
            fadc_data.adc_sum = (data & 0x3FFFFF)
            if data & 0x400000:
                fadc_data.over = 1
            if verbose:
                print(f"{data:08X} - WINDOW SUM - chan = {fadc_data.chan}   "
                      f"over = {fadc_data.over}   adc_sum = {fadc_data.adc_sum:08x}")

        elif t == 6:  # PULSE RAW DATA
            if fadc_data.new_type:
                self.data_type_6 = 1
                fadc_data.chan       = (data & 0x07800000) >> 23
                fadc_data.pulse_num  = (data & 0x600000) >> 21
                fadc_data.thres_bin  = (data & 0x3FF)

                if fadc_data.chan < self.FADC_NCHAN:
                    self.fadc_nhit[fadc_data.chan] += 1
                else:
                    print(f"FADC: Something wrong here! chan {fadc_data.chan+1} > FADC_NCHAN ({self.FADC_NCHAN})")

                if verbose:
                    print(f"{data:08X} - PULSE RAW DATA - chan = {fadc_data.chan}   "
                          f"pulse # = {fadc_data.pulse_num}   threshold bin = {fadc_data.thres_bin}")
            else:
                fadc_data.valid_1 = 1
                fadc_data.valid_2 = 1
                fadc_data.adc_1   = (data & 0x1FFF0000) >> 16
                if data & 0x20000000:
                    fadc_data.valid_1 = 0
                fadc_data.adc_2   = (data & 0x1FFF)
                if data & 0x2000:
                    fadc_data.valid_2 = 0
                if verbose:
                    print(f"{data:08X} - PULSE RAW SAMPLES - valid = {fadc_data.valid_1}  "
                          f"adc = {fadc_data.adc_1}   valid = {fadc_data.valid_2}  adc = {fadc_data.adc_2}")

        elif t == 7:  # PULSE INTEGRAL
            self.data_type_7   = 1
            fadc_data.chan     = (data & 0x07800000) >> 23
            fadc_data.pulse_num= (data & 0x600000) >> 21
            fadc_data.quality  = (data & 0x180000) >> 19
            fadc_data.integral = (data & 0x7FFFF)

            if fadc_data.chan < self.FADC_NCHAN:
                self.fadc_nhit[fadc_data.chan] += 1
                hit_count = self.fadc_nhit[fadc_data.chan]
                if hit_count == 1:
                    self.fadc_int[fadc_data.chan] = fadc_data.integral
                elif hit_count == 2:
                    self.fadc_int_1[fadc_data.chan] = fadc_data.integral
                elif hit_count > self.MAXHIT:
                    print(f"FADC:  Too many ADC hits ({hit_count} hits) in chan {fadc_data.chan}")

                if self.fadc_nhit[fadc_data.chan] != self.ftdc_nhit[fadc_data.chan]:
                    print(f"FADC:  Warning:  TDC hits {self.ftdc_nhit[fadc_data.chan]} != "
                          f"ADC hits {self.fadc_nhit[fadc_data.chan]}")
            else:
                print(f"FADC: Something wrong here! ADC chan {fadc_data.chan+1} > FADC_NCHAN ({self.FADC_NCHAN})")

            if verbose:
                print(f"{data:08X} - PULSE INTEGRAL - chan = {fadc_data.chan}   pulse # = {fadc_data.pulse_num}   "
                      f"quality = {fadc_data.quality}   integral = {fadc_data.integral}")

        elif t == 8:  # PULSE TIME
            self.data_type_8   = 1
            fadc_data.chan     = (data & 0x07800000) >> 23
            fadc_data.pulse_num= (data & 0x600000) >> 21
            fadc_data.quality  = (data & 0x180000) >> 19
            fadc_data.time     = (data & 0xFFFF)

            if fadc_data.chan < self.FADC_NCHAN:
                self.ftdc_nhit[fadc_data.chan] += 1
                hit_count = self.ftdc_nhit[fadc_data.chan]
                if hit_count == 1:
                    self.fadc_time[fadc_data.chan] = fadc_data.time
                elif hit_count == 2:
                    self.fadc_time_1[fadc_data.chan] = fadc_data.time
                elif hit_count > self.MAXHIT:
                    print(f"FADC:  Too many TDC hits ({hit_count} hits) in chan {fadc_data.chan}")
            else:
                print(f"FADC: Something wrong here! TDC chan {fadc_data.chan+1} > FADC_NCHAN ({self.FADC_NCHAN})")

            if verbose:
                print(f"{data:08X} - PULSE TIME - chan = {fadc_data.chan}   pulse # = {fadc_data.pulse_num}   "
                      f"quality = {fadc_data.quality}   time = {fadc_data.time}")

        elif t == 9:  # STREAMING RAW DATA
            if fadc_data.new_type:
                fadc_data.chan_a    = (data & 0x3C00000) >> 22
                fadc_data.source_a  = (data & 0x4000000) >> 26
                fadc_data.chan_b    = (data & 0x1E0000) >> 17
                fadc_data.source_b  = (data & 0x200000) >> 21
                if verbose:
                    print(f"{data:08X} - STREAMING RAW DATA - ena A = {fadc_data.source_a}  "
                          f"chan A = {fadc_data.chan_a}   ena B = {fadc_data.source_b}  "
                          f"chan B = {fadc_data.chan_b}")
            else:
                fadc_data.valid_1 = 1
                fadc_data.valid_2 = 1
                fadc_data.adc_1   = (data & 0x1FFF0000) >> 16
                if data & 0x20000000:
                    fadc_data.valid_1 = 0
                fadc_data.adc_2   = (data & 0x1FFF)
                if data & 0x2000:
                    fadc_data.valid_2 = 0
                fadc_data.group   = (data & 0x40000000) >> 30

                if fadc_data.group:
                    if verbose:
                        print(f"{data:08X} - RAW SAMPLES B - valid = {fadc_data.valid_1}  adc = {fadc_data.adc_1}   "
                              f"valid = {fadc_data.valid_2}  adc = {fadc_data.adc_2}")
                else:
                    if verbose:
                        print(f"{data:08X} - RAW SAMPLES A - valid = {fadc_data.valid_1}  adc = {fadc_data.adc_1}   "
                              f"valid = {fadc_data.valid_2}  adc = {fadc_data.adc_2}")

        elif t == 10:  # PULSE AMPLITUDE DATA
            fadc_data.chan      = (data & 0x07800000) >> 23
            fadc_data.pulse_num = (data & 0x600000) >> 21
            fadc_data.vmin      = (data & 0x1FF000) >> 12
            fadc_data.vpeak     = (data & 0xFFF)
            if verbose:
                print(f"{data:08X} - PULSE V - chan = {fadc_data.chan}   pulse # = {fadc_data.pulse_num}   "
                      f"vmin = {fadc_data.vmin}   vpeak = {fadc_data.vpeak}")

        elif t == 11:  # INTERNAL TRIGGER WORD
            fadc_data.trig_type_int  = data & 0x7
            fadc_data.trig_state_int = (data & 0x8) >> 3
            fadc_data.evt_num_int    = (data & 0xFFF0) >> 4
            fadc_data.err_status_int = (data & 0x10000) >> 16
            if verbose:
                print(f"{data:08X} - INTERNAL TRIGGER - type = {fadc_data.trig_type_int}   "
                      f"state = {fadc_data.trig_state_int}   num = {fadc_data.evt_num_int}   "
                      f"error = {fadc_data.err_status_int}")

        elif t == 12:  # UNDEFINED TYPE (here used for SCALER, apparently)
            if fadc_data.new_type:
                fadc_data.num_scaler = data & 0x3F
                if fadc_data.num_scaler != 18:
                    print(f"FADC ERROR: the number of words for scaler {fadc_data.num_scaler} is not 18")
                if verbose:
                    print(f"{data:08X} - TYPE 12 first word NUM of SCALER WORDS = {fadc_data.num_scaler}")
                self.nscalwrd = 0
            else:
                if self.nscalwrd < 16:
                    self.fadc_scal_cnt[self.nscalwrd] = data
                if self.nscalwrd == 16:
                    self.fadc_scal_time = data
                if self.nscalwrd == 17:
                    self.fadc_scal_trigcnt = data
                    self.fadc_scal_update = 1
                if self.nscalwrd > 17:
                    print("FADC ERROR: the scaler words is bigger than 18")

                if verbose:
                    print(f"{data:08X} - TYPE 12 {self.nscalwrd} word = {data}")
                self.nscalwrd += 1

        elif t == 13:  # END OF EVENT
            if verbose:
                print(f"{data:08X} - END OF EVENT = {fadc_data.type}")

        elif t == 14:  # DATA NOT VALID
            if verbose:
                print(f"{data:08X} - DATA NOT VALID = {fadc_data.type}")

        elif t == 15:  # FILLER WORD
            if verbose:
                print(f"{data:08X} - FILLER WORD = {fadc_data.type}")

        # update type_last
        self.type_last = fadc_data.type
