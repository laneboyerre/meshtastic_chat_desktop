import pathlib
import getpass
from platformdirs import user_data_dir
import os
import logging

logger = logging.getLogger()
class StorageManager():
    
    def __init__(self, debug=False, dev=False) -> None:
        app_data_folder = ""
        if dev:
            app_data_folder = './program_data'
        else:
            user = getpass.getuser()
            app_data_folder, _ = os.path.split(user_data_dir(appname="MeshtasticChatDesktop", 
                                           appauthor=None))
        logger.debug(f"Set application data folder to: {app_data_folder}") 
        if not os.path.exists(app_data_folder):
            logger.info(f"Application data folder does not exist in {app_data_folder}, creating one...")
            os.makedirs(app_data_folder)