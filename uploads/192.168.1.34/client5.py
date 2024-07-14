import requests
import json
import os
import threading
from flask import Flask, request
import base64

def start_client_server(subscriber_port):
    app = Flask(__name__)

    @app.route('/receive', methods=['POST'])
    def receive():
        data = request.json
        print("Received message from server:", data)
        return "Message received", 200

    app.run(host='0.0.0.0', port=subscriber_port, debug=False)

def main():
    server_ip = input("Enter server IP: ")
    server_port = input("Enter server port: ")
    base_url = f"http://{server_ip}:{server_port}/send"
    
    subscriber_ip = input("Enter your IP address: ")
    subscriber_port = int(input("Enter port number to receive messages: "))
    subscriber_id = f"http://{subscriber_ip}:{subscriber_port}/receive"

    # Start the Flask client server in a separate thread
    threading.Thread(target=start_client_server, args=(subscriber_port,)).start()

    while True:
        print("\nOptions:")
        print("1. Send text message")
        print("2. Send group message")
        print("3. Send data message")
        print("4. Send file")
        print("5. Subscribe")
        print("6. Unsubscribe")
        print("7. Exit")
        choice = input("Choose an option: ")

        if choice == '1':
            destination_id = input("Enter destination ID: ")
            text_message = input("Enter text message: ")
            channel_index = input("Enter channel index (default 0): ")
            channel_index = int(channel_index) if channel_index else 0

            payload = {
                "destination_id": destination_id,
                "text_message": text_message,
                "channel_index": channel_index
            }

        elif choice == '2':
            group_message = input("Enter group message: ")
            channel_index = input("Enter channel index (default 0): ")
            channel_index = int(channel_index) if channel_index else 0

            payload = {
                "group_message": group_message,
                "channel_index": channel_index
            }

        elif choice == '3':
            destination_id = input("Enter destination ID: ")
            data_message = input("Enter data message: ")
            channel_index = input("Enter channel index (default 0): ")
            channel_index = int(channel_index) if channel_index else 0

            payload = {
                "destination_id": destination_id,
                "data_message": data_message,
                "channel_index": channel_index
            }

        elif choice == '4':
            destination_id = input("Enter destination ID: ")
            file_path = input("Enter file path: ")
            channel_index = input("Enter channel index (default 0): ")
            channel_index = int(channel_index) if channel_index else 0

            if not os.path.isfile(file_path):
                print("Invalid file path. Please try again.")
                continue

            payload = {
                "destination_id": destination_id,
                "file_message": {
                    "name": os.path.basename(file_path),
                    "content": base64.b64encode(open(file_path, 'rb').read()).decode('utf-8')
                },
                "channel_index": channel_index
            }

        elif choice == '5':
            verbose = input("Verbose mode (y/n): ").lower() == 'y'

            payload = {
                "subscribe": subscriber_id,
                "subscriber_port": subscriber_port,
                "verbose": verbose
            }

        elif choice == '6':
            payload = {
                "unsubscribe": subscriber_id
            }

        elif choice == '7':
            print("Exiting...")
            break

        else:
            print("Invalid choice. Please try again.")
            continue

        response = requests.post(base_url, json=payload)
        print("Server response:", response.json())

if __name__ == "__main__":
    main()
