
from Class.friends_modules.GenericFriendDataInterface import GenericFriendDataInterface
import os
import pickle

DATA_FOLDER = './program_data'
PICKLE_FILE_NAME = 'friends.pickle'

class PickleFriendInterface(GenericFriendDataInterface):
    
    def __init__(self, folder = DATA_FOLDER) -> None:
        self.data_folder = folder
        self.file_location = f"{self.data_folder}/{PICKLE_FILE_NAME}"
    
    def load(self):
        if os.path.exists(self.file_location):
            with open(self.file_location, 'rb') as handle:
                return pickle.load(handle)
        else:
            return {}
        
    def save(self, friends_dictionary):
        with open(self.file_location, 'wb') as handle:
            pickle.dump(friends_dictionary, handle, protocol=pickle.HIGHEST_PROTOCOL)
            
    def update(self):
        pass