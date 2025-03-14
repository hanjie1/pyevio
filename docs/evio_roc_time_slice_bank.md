
# ROC Time Slice Bank

ROC Time Slice Bank

![[evio_roc_tsb.png]]

File consists of

-  "ROC Time Slice Bank" that has:
    - Header
    - Stream Info Bank (SIB)
    - Data Banks

I "ROC Time Slice Bank"-Header structure:
- 1st word (32 bit) - ROC Bank Length
- 2nd word (32 bit) - ROC_ID, 0x10, SS. In particular:
    - First 16 bit ROC ID
    - 0x10 - means Bank of banks
    - SS (8 bits) - Stream Status. Bits 7 - error or not, Bits 6-4 Total Strams, Bits 3-0 Stream Mask

II "Stream Info Bank (SIB)" - Structure:
- 1st word (32 bit) - Stream Info Length
- 2nd word (32 bit) - 0xFF30, 0x20, SS (same as above)
- Time slice segment (TSS) words:
    1. TSS Header: 0x31, 0x01, TSS Len (16 bits)
    2. Frame Number (32 bit)
    3. Timestamp (31-0)
    4. Timestamp (63-32)
- Aggregation Info Segment (AIS):
    1. AIS Header - 0x41, 0x85, AIS Len. (!) Important here - 2nd byte: top 2 bits = 2 for padding if odd # payloads (else 0), lower 6 bits is type 5 (unsigned short) => 0x85 (1000 0101)
    2. All other words - Payloads infos in 16 bit half-words. Number of payload infos is given in AIS Len. Since we read 32 bits, payloads go like (Payload2, Payload1) - word 1, (Payload4, Payload3) - word 2. If number of payloads is odd, the last word will be (0, PayloadN). There can't be more than 20 Payload infos in one AIS. Now how what is Payload info consists of:
       - bits 11-8 - Module ID
       - Bond? - 7
       - Lane ID - 6, 5
       - Payload Port # - 4-0

III  "Data Bansks" structure (words):
1. Payload Port (PP) 1 Length
2. PP 1 ID, 0x0,  SS
... PP 1 DATA
...
- Payload Port N Length
- 5PP N ID, 0x0, SS PP N Data
		
	
	
  