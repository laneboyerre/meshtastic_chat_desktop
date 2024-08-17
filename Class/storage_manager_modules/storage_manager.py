import json
from platformdirs import user_data_dir
import os
import logging

logger = logging.getLogger()

SETTINGS_FILE = 'settings.json'
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
            
        self.settings_path = f"{self.app_data_folder}/{SETTINGS_FILE}"
        if not os.path.exists(self.settings_path):
            with open(self.settings_path, mode="w") as file:
                json.dump({}, file)
                logger.info(f"Could not find settings.json file, creating one in {self.settings_path}")
        else:
            logger.info(f"Found settings.json file")

        
class SettingsManager():
    
    def __init__(self, path) -> None:
        self.settings_path = path
        self.settings = self.load()
        
    def load(self):
        with open(self.settings_path) as settings_file:
            return json.load(settings_file)
        
    def save(self):
        with open(self.settings_path, mode="w") as settings_file:
            return json.dump(self.settings, settings_file, indent=4, sort_keys=True)
        
        