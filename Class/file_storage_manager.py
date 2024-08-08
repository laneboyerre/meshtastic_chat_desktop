"""land_and_air: 8/7/24
utility class for Managing files the server knows about both locally and remotely."""
import pandas as pd

class FileStorageManager:
    def __init__(self, log_path, store_dir):
        self.save_path = log_path
        self.store_dir = store_dir
        self.hdf_store = pd.HDFStore(log_path, 'a', complevel=1)

    def add_file(self, source: str, hash_int: int, file_size: int, path: str, file_content):
        if source in self.hdf_store:
            df = self.hdf_store[source]
        else:
            df = pd.DataFrame()
        self.hdf_store[source] = df
        return df

    def get_file_info(self, hash_int: int, file_size: int):
        for server in self.hdf_store:
            df = self.hdf_store[server]
            print(df)

    def close(self):
        self.hdf_store.close()


if __name__ == '__main__':
    file_manager = FileStorageManager('test.hdf', 'Test')
