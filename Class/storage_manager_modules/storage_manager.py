import pathlib
import getpass
from platformdirs import user_data_dir
import os
import logging

logger = logging.getLogger()
class StorageManager():
    
    def __init__(self, debug=False, dev=False) -> None:
        self.app_data_folder = ""
        if dev:
            self.app_data_folder = './program_data'
        else:
            self.app_data_folder, _ = os.path.split(user_data_dir(appname="MeshtasticChatDesktop", 
                                           appauthor=None))
        logger.debug(f"Set application data folder to: {self.app_data_folder}") 
        if not os.path.exists(self.app_data_folder):
            logger.info(f"Application data folder does not exist in {self.app_data_folder}, creating one...")
            os.makedirs(self.app_data_folder)