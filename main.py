#main.py
from Class.meshtastic_chat_app import MeshtasticChatApp

if __name__ == "__main__":
	dev_path = '/dev/ttyUSB0'
	destination_id = "!fa6a40a8"
	app = MeshtasticChatApp(dev_path, destination_id)
	app.run()
