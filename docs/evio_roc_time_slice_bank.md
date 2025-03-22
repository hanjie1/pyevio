
# ROC Time Slice Bank

ROC Time Slice Bank

![[evio_roc_tsb.png]]

-  "ROC Time Slice Bank" that has:
    - Header
    - Stream Info Bank (SIB)
    - Data Banks

I "ROC Time Slice Bank"-Header structure:
- 1st word (32 bit) - ROC Bank Length
- 2nd word (32 bit) - ROC_ID, 0x10, SS. In particular:
    - First 16 bit ROC ID
    - 0x10 - means Bank of banks
    - SS (8 bits) - Stream Status. Bits 7 - error or not, Bits 6-4 Total Streams, Bits 3-0 Stream Mask

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


Let me explain what happens and how we should scan banks:

Here is the full event hex dump
```
0    0x00055118 87110   00 00 00 15        0    21              21   ....            
1    0x0005511c 87111   ff 60 10 01    65376  4097      4284485633   .`..            
2    0x00055120 87112   00 00 00 07        0     7               7   ....            
3    0x00055124 87113   ff 31 20 01    65329  8193      4281409537   .1 .            
4    0x00055128 87114   32 01 00 03    12801     3       838926339   2...            
5    0x0005512c 87115   00 00 00 00        0     0               0   ....            
6    0x00055130 87116   00 00 00 00        0     0               0   ....            
7    0x00055134 87117   00 00 00 00        0     0               0   ....            
8    0x00055138 87118   42 01 00 01    16897     1      1107361793   B...            
9    0x0005513c 87119   00 02 00 11        2    17          131089   ....            
10   0x00055140 87120   00 00 00 0b        0    11              11   ....            
11   0x00055144 87121   00 02 10 11        2  4113          135185   ....            
12   0x00055148 87122   00 00 00 07        0     7               7   ....            
13   0x0005514c 87123   ff 30 20 11    65328  8209      4281344017   .0 .            
14   0x00055150 87124   31 01 00 03    12545     3       822149123   1...            
15   0x00055154 87125   00 00 00 00        0     0               0   ....            
16   0x00055158 87126   00 00 00 00        0     0               0   ....            
17   0x0005515c 87127   00 00 00 00        0     0               0   ....            
18   0x00055160 87128   41 85 00 01    16773     1      1099235329   A...            
19   0x00055164 87129   00 00 00 00        0     0               0   ....            
20   0x00055168 87130   00 00 00 01        0     1               1   ....            
21   0x0005516c 87131   00 0f 00 01       15     1          983041   ....
```

We start with event length and header

```
87110   00 00 00 15
87111   ff 60 10 01
```

If we count `0x15=21` we will jump to the last word of the event.

Now goes the first bank:
87112   00 00 00 07 - it says the bank content is the next 7 words and the last bank word is at offset 87119   
Read the next line. It is still inside event? Then it should be the next bank length.
87120   00 00 00 0b where 0xb=11. If we add 11 to the offset we correctly jump to offset 87131   which is the last word of the event. Bingo! Our event banks structure validated!

Now we come back and see what bank is that?

```
11   0x00055144 87121   00 02 10 11        2  4113          135185   ....            
12   0x00055148 87122   00 00 00 07        0     7               7   ....
```
0x10 means it is a bank of banks. So we can jump in and see the the first child bank is FF30 - streaming!

Now if we look at header we see

I "ROC Time Slice Bank"-Header structure:
- 1st word (32 bit) - ROC Bank Length
- 2nd word (32 bit) - ROC_ID, 0x10, SS. In particular:
    - First 16 bit ROC ID
    - 0x10 - means Bank of banks
    - SS (8 bits) - Stream Status. Bits 7 - error or not, Bits 6-4 Total Streams, Bits 3-0 Stream Mask

Which means that 00 02 is ROC_ID and  0x11 is a status code

00 00 00 07        0     7  - Stream Info bank length so it goes to the last line  87129   00 00 00 00        0     0               0, which is actually payload1 AIS record with module id = 0

FInally we have the final bank. The first line says it is 1 word which is 00 0f 00 01 - our payload

```
20   0x00055168 87130   00 00 00 01        0     1               1   ....            
21   0x0005516c 87131   00 0f 00 01       15     1          983041   ....
```

Conclusion:
We find banks by taking first word and calculating where bank ends and validate that the end should correspond to our event end, another bank end, etc. 



  