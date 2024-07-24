"""land_and_air: 7/21/24
utility class for packing and unpacking data from byte strings into the resulting data for each type."""
import struct
import math
import hashlib
import os

class DataPackager:
    """Packages and decodes data to be sent over the mesh"""
    def __init__(self, path_length=64):
        self.frequency = self.set_frequency(6.25)
        self.max_requests = 64  # max number of retransmissions allowed
        self.path_length = path_length
        self.data_packet_format = '>xxxIH'
        self.file_id_format = '>xxxIIH'
        self.hash_format = '>xxxI'
        self.file_req_format = '>xxxIIB'
        self.file_retrans_format = '>xxxIBB'
        self.speed_update = '>xxxB'

    def set_frequency(self, seconds: float):
        """Uses an exponential function to maximize both range and definition"""
        self.frequency = round(math.log(seconds/100)/math.log(.95))
        return self.frequency

    def get_file_breakdown(self, path):
        """gets the following:
         - 4 byte hash
         - 4 byte file size
         - n byte representation of file name
         - file content"""
        with open(path, 'rb') as f:
            content = f.read()
            file_size = len(content)
            max_size, = struct.unpack('>I', b'\xff\xff\xff\xff')
            h = hashlib.blake2s(f.read(), digest_size=4)
            if file_size > max_size:
                file_size = -1  # too big deny request
            else:
                file_size = struct.pack('>I', file_size)  # size in bytes
        if len(path) > self.path_length:
            path = self.shorten_path(path)
        return h.digest(), file_size, path, content

    def shorten_path(self, path):
        dirs, path = os.path.split(path)
        path, ext = os.path.splitext(path)
        non_file = len(dirs) + len(ext)
        if self.path_length-non_file < 0:
            print('path shortening failed')
        path = path[:self.path_length-non_file]
        return os.path.join(dirs, path+ext)

    def decode_frequency_bytes(self, n=None):
        """
        Input int for frequency or get the current wait time last set
        """
        if n:
            self.frequency = n
        return .95**self.frequency * 100

    def decode_file_hash(self, b: bytes):
        """gets file hash from file packet"""
        size = struct.calcsize(self.hash_format)
        hash, = struct.unpack(self.hash_format, b[:size])
        return hash

    def encode_file_hash(self, prefix, h: int):
        b = struct.pack(self.hash_format, h) # encode hash
        b = prefix + b[3:]  # Add prefix to beginning
        return b

    def decode_speed_update(self, b: bytes):
        """decode speed update packet NCR[n]"""
        size = struct.calcsize(self.speed_update)
        n_rate, = struct.unpack(self.speed_update, b[:size])
        frequency = self.decode_frequency_bytes(n_rate)
        return frequency

    def encode_speed_update(self, prefix):
        n_rate = self.frequency
        b = struct.pack(self.speed_update, n_rate)
        b = prefix + b[3:]
        return b

    def decode_data_packet(self, b: bytes):
        """
        Use on a data packet like 'FCD'
        Returns file hash, packet index, and file_data
        '>IH' to get hash and index
        """
        size = struct.calcsize(self.data_packet_format)
        file_hash, index = struct.unpack(self.data_packet_format, b[:size])
        return file_hash, index, b[size:]

    def encode_data_packet(self, prefix, file_hash, index, data):
        b = struct.pack(self.data_packet_format, file_hash, index)
        b += data
        b = prefix + b[3:]
        return b

    def decode_file_announce(self, b: bytes):
        """
        Use on a data packet like 'FCI'
        Returns file hash, packet index, and file_data
        '>II' to get hash and file size
        """
        size = struct.calcsize(self.file_id_format)
        file_hash, file_size, num_chunks = struct.unpack(self.file_id_format, b[:size])
        file_name = b[size:].decode('utf8')
        return file_hash, file_size, num_chunks, file_name

    def encode_file_announce(self, prefix, file_hash, file_size, num_chunks, path):
        """
        Use on a data packet like 'FCI'
        Returns encoded binary message
        """
        b = struct.pack(self.file_id_format, file_hash, file_size, num_chunks)
        b += path.encode('utf8')
        b = prefix + b[3:]
        return b

    def decode_file_req_speed(self, b: bytes):
        """gets data about the hash and the request FCR[hash][num][n]"""
        size = struct.calcsize(self.file_req_format)
        file_hash, file_size, n_rate = struct.unpack(self.file_req_format, b[:size])
        frequency = self.decode_frequency_bytes(n_rate)
        return file_hash, file_size, frequency

    def encode_file_req_speed(self, prefix, file_hash, file_size):
        """encodes data about the hash and the request FCR[hash][num][n]"""
        b = struct.pack(self.file_req_format, file_hash, file_size, self.frequency)
        b = prefix + b[3:]
        return b

    def decode_file_retrans_req(self, b: bytes):
        """
            Use on a data packet like 'FCQ'
            Returns file hash, packet index, and file_data
            '>IBB' to get hash, rate
        """
        size = struct.calcsize(self.file_retrans_format)
        file_hash, n_rate, percent_received = struct.unpack(self.file_retrans_format, b[:size])
        frequency = self.decode_frequency_bytes(n_rate)
        percent_received = int(percent_received)/255 * 100
        fmt = 'H' * int(len(b[size:])/2)
        missed_packets = struct.unpack('>'+fmt, b[size:])
        return file_hash, frequency, percent_received, missed_packets

    def encode_file_retrans_req(self, prefix, file_hash, percent_received, missed_packets):
        """encodes missing data about the hash and the request FCR[hash][num][n]"""
        percent_num = round(percent_received * 255 / 100)
        b = struct.pack(self.file_retrans_format, file_hash, self.frequency, percent_num)
        b = prefix + b[3:]
        missed_packets = missed_packets[:self.max_requests]
        fmt = 'H' * len(missed_packets)
        b += struct.pack('>' + fmt, *missed_packets)
        return b

    def decode_server_announce(self, b: bytes):
        """
            Use on a data packet like 'NCA'
            Returns server name
        """
        return b[3:].decode('utf8')

    def encode_server_announce(self, prefix, server_name):
        """
            Use on a data packet like 'NCA'
            Returns server name
        """
        b = prefix + server_name.encode('utf8')
        return b


if __name__ == '__main__':
    data = DataPackager()
    hz = data.decode_frequency_bytes(0)
    print(f'hz: {hz}')
    file_hash, index, d = data.decode_data_packet(b'FCD\x00\x00\x00\x01\x00\x01123456')
    print("FCD", file_hash, index, d)
    b = data.encode_data_packet(b'FCD', file_hash, index, d)
    print(f'file_data_message: {b}')
    h = data.decode_file_hash(b'FCE6\xe9\xd2F')
    print(f'hash: {h}')
    b = data.encode_file_hash(b'FCE', h)
    print(f'file_end_hash: {b}')
    frequency = data.decode_speed_update(b'NCR\x01')
    print("NCR", frequency)
    data.set_frequency(frequency)
    b = data.encode_speed_update(b'NCR')
    print("frequency message:", b)
    h = data.get_file_breakdown('data_packager.py'.encode('utf8'))
    print(f'hash: {h}')
    file_hash, file_size, num_chunks, file_name = data.decode_file_announce(b'FCI6\xe9\xd2F\x00\x00\r+\x01\x00Filename.py')
    print("FCI", file_hash, file_size, num_chunks, file_name)
    b = data.encode_file_announce(b'FCI', file_hash, file_size, num_chunks, file_name)
    print("File info packet:", b)
    file_hash, file_size, frequency = data.decode_file_req_speed(b'FCR6\xe9\xd2F\x00\x00\r+\xff')
    print("FCR", file_hash, file_size, frequency)
    data.set_frequency(frequency)
    b = data.encode_file_req_speed(b'FCR', file_hash, file_size)
    print("File request packet:", b)
    file_hash, frequency, percent_received, missed_packets = data.decode_file_retrans_req(b'FCQ6\xe9\xd2F\x01\xff121314')
    print("FCQ", file_hash, frequency, percent_received, missed_packets)
    data.set_frequency(frequency)
    b = data.encode_file_retrans_req(b'FCQ', file_hash, percent_received, missed_packets)
    print("File retransmission packet:", b)
    server_name = data.decode_server_announce(b'NCAServer1')
    print("NCA", server_name)
    b = data.encode_server_announce(b'NCA', server_name)
    print("File server announcement:", b)
