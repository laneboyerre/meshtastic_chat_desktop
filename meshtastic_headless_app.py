import threading
import json
import os
import base64
import argparse
import time

from Class.meshtastic_chat_app import MeshtasticChatApp  # Import your existing class
import platform

CHUNK_SIZE = 100  # Define CHUNK_SIZE here
STYLE = 'default'  # Set the style to be used for the ttk widgets


def main(args):
    device_path = args.device_path
    timeout = args.timeout
    retransmission_limit = args.retrans_limit

    chat_iface = MeshtasticHeadlessInterface(device_path, timeout, retransmission_limit)
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:  # Closing program
        chat_iface.chat_app.interface.close()


class MeshtasticHeadlessInterface:
    """Interface for starting the webserver through just the command line"""
    def __init__(self, device_path, timeout, retransmission_limit=2):
        self.device_path = device_path
        self.destination_id = ""  # Unsure of its use
        self.timeout = timeout
        self.retransmission_limit = retransmission_limit
        self.chat_app = self.connect_device()
        self.chat_app.start_flask_server()

    def connect_device(self):
        chat_app = MeshtasticChatApp(
            dev_path=self.device_path,
            destination_id="",
            on_receive_callback=self.update_output,
            timeout=self.timeout,
            retransmission_limit=self.retransmission_limit
        )
        self.update_output("Connected to the Meshtastic device successfully.")
        return chat_app

    def update_output(self, message, message_type="INFO"):
        # Update message history for received messages
        if message_type == "RECEIVED":
            print(f'Recieved: {message}')
        # Print to the terminal as well
        # print(message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='Meshtastic headless file server',
        description='Headless version of meshtastic_tkinter_app.py', )
    parser.add_argument('device_path', help='com port to the meshtastic device')
    parser.add_argument('-r', '--retrans_limit', default=2, help='Number of tries before giving up')
    parser.add_argument('-t', '--timeout', default=30, help='Time between packets before giving up')
    parser.add_argument('-c', '--config_file', help='Json file of input args to be used in place of args')
    parser.add_argument('--save_to_config', action='store_true', help='Saves input args to config path specified')

    args = parser.parse_args()
    main(args)