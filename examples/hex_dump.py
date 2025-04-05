import mmap
import os

from pyevio.utils import print_offset_hex


def main():
    filename = r"D:\data\gemtrd\hd_rawdata_003101_000.evio"
    file = open(filename, 'rb')
    file_size = os.path.getsize(filename)
    mm = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
    print_offset_hex(mm, 0, 64, "First words", ">")


if __name__ == "__main__":
    main()

