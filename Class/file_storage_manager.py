"""land_and_air: 8/7/24
utility class for Managing files the server knows about both locally and remotely."""
import os.path
import pandas as pd

class FileStorageManager:
    def __init__(self, log_path, store_dir):
        self.save_path = log_path
        self.make_dir(store_dir)
        self.store_dir = store_dir
        self.hdf_store = pd.HDFStore(log_path, 'a', complevel=1)

    def make_dir(self, path):
        if not os.path.exists(path):
            os.mkdir(path)

    def add_file(self, source: str, hash_int: int, file_size: int, path: str, file_content):
        # Add file to store_dir if content exists
        if file_content:
            file_dir = os.path.join(self.store_dir, source)
            self.make_dir(file_dir)
            with open(os.path.join(file_dir, f'{hash_int}_{path}'), 'wb') as f:
                f.write(file_content)
        # Add file to dir
        content_dict = {'hash_int': hash_int,
                        'file_size': [file_size],
                        'path': [path],
                        'has_file_content': [bool(file_content)]
                        }
        if source in self.hdf_store:
            df = self.hdf_store[source]
            new_row = pd.DataFrame().from_dict(content_dict)
            df = pd.concat([df, new_row]).drop_duplicates()
        else:
            df = pd.DataFrame().from_dict(content_dict)
        self.hdf_store[source] = df
        return df

    def get_file_content(self, hash_int: int, file_size: int):
        for server in self.hdf_store:
            df = self.hdf_store[server]
            matching_hash = df[df['hash_int'] == hash_int]
            matching_file = matching_hash[matching_hash['file_size'] == file_size]
            if len(matching_file):
                has_file_content = matching_file['has_file_content']
                file_content = None
                path = matching_file['path'][0]
                if has_file_content.any():
                    file_dir = os.path.join(self.store_dir, server.strip('/'))
                    file_path = os.path.join(file_dir, f'{hash_int}_{path}')
                    with open(file_path, 'rb') as f:
                        file_content = f.read()
                return server, path, file_content
        return None

    def combine_info_hdf(self, new_hdf_path: str):
        new_store = pd.HDFStore(new_hdf_path, 'r')
        for source in new_store:
            new_df = new_store[source]
            if source in self.hdf_store:
                old_df = self.hdf_store[source]
            else:
                old_df = pd.DataFrame()
            # Concatenating two dataframes without duplicates
            new_dataframe = pd.concat([old_df, new_df]).drop_duplicates()

            # Resetting index
            new_dataframe = new_dataframe.reset_index(drop=True)
            self.hdf_store[source] = new_dataframe

    def close(self):
        self.hdf_store.close()


if __name__ == '__main__':
    file_manager = FileStorageManager('test.hdf', 'Test')
    print(file_manager.add_file('s123456', 123456, 10_000, 'Test_File.txt', b'content'))
    print(file_manager.add_file('s54321', 54321, 10_000, 'Test_File.txt', None))
    print(file_manager.get_file_content(123456, 10_000))
    print(file_manager.get_file_content(54321, 10_000))
    file_manager.close()
