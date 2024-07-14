import meshtastic
import meshtastic.serial_interface
import logging
import threading
import os
import json
from pubsub import pub
from colorama import Fore, Style, init
from typing import Union, Optional, Callable
from meshtastic import channel_pb2, portnums_pb2, mesh_pb2
import time
from datetime import datetime
import timeago
import base64
import google.protobuf.json_format
import platform
import requests
from Flask.flask_server import start_heartbeat_monitor
from flask_socketio import SocketIO, emit

# Initialize colorama
init(autoreset=True)

if platform.system() == "Linux":
    from meshtastic.tunnel import Tunnel  # Import the Tunnel class

# Enable logging but set to ERROR level to suppress debug/info messages
logging.basicConfig(level=logging.ERROR)

FILE_IDENTIFIER = b'FILEDATA:'
ANNOUNCE_IDENTIFIER = b'FILEINFO:'
IPDATA_IDENTIFIER = b'IPDATA:'
CHUNK_SIZE = 100  # Chunk size in bytes
BROADCAST_ADDR = "^all"
MAX_RETRIES = 5

class MeshtasticChatApp:
    def __init__(self, dev_path, destination_id, on_receive_callback=None, timeout=10, retransmission_limit=3):
        self.dev_path = dev_path
        self.destination_id = destination_id
        self.timeout = timeout
        self.retransmission_limit = retransmission_limit
        self.interface = None
        self.received_chunks = {}
        self.acknowledged_chunks = set()
        self.expected_chunks = {}
        self.on_receive_callback = on_receive_callback
        self.tunnel = None  # Initialize the tunnel attribute
        self._acknowledgment = type('', (), {})()  # Create an empty object to hold acknowledgment flags
        self._acknowledgment.receivedTraceRoute = False
        self.retry_counts = {}  # Track the number of retries for each file
        self.subscribers = {}  # To hold subscribers for forwarding messages
        self.sent_chunks = {}  # To store sent chunks temporarily
        self.flask_server_running = False
        # Connect to the Meshtastic device
        try:
            self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.dev_path)
            print(Fore.LIGHTBLACK_EX + "Connected to the Meshtastic device successfully.")
        except Exception as e:
            print(Fore.LIGHTBLACK_EX + f"Failed to connect to the Meshtastic device: {str(e)}")
            exit(1)
        
        # Subscribe to received message events
        pub.subscribe(self.on_receive, "meshtastic.receive")

    def set_destination_id(self, destination_id):
        self.destination_id = destination_id

    # Callback function to handle acknowledgment
    def on_ack(self, response, event):
        print(Fore.GREEN + "Acknowledgment received!")
        event.set()  # Signal that acknowledgment has been received
        if self.on_receive_callback:
            self.on_receive_callback("Acknowledgment received!", message_type="SUCCESS")
                    
    def on_receive(self, packet, interface):
        try:
            if 'decoded' in packet:
                decoded = packet['decoded']
                if 'payload' in decoded and isinstance(decoded['payload'], bytes):
                    try:
                        data = decoded['payload']
                        sender_id = packet.get('fromId', packet['from'])  # Use 'fromId' if available, otherwise fallback to 'from'
                        print(Fore.LIGHTBLUE_EX + f"Received data: {data[:50]}... from {sender_id}")

                        # Forward received data to subscribers
                        if self.subscribers:
                            self.forward_to_subscribers(sender_id, data.decode('utf-8'), packet)
                        
                        if data.startswith(IPDATA_IDENTIFIER):
                            # Extract IP data and forward to web clients
                            ip_data = data.split(b':', 3)[-1].decode('utf-8')
                            self.forward_ip_data_to_clients(ip_data)
                        
                        if data.decode('utf-8').startswith('IPREQ:'):
                            # Handle IP data request
                            url = data.decode('utf-8').split(':', 1)[1]
                            self.send_ip_data_in_chunks(url, destination_id=sender_id, channel_index=0)

                        if data.startswith(ANNOUNCE_IDENTIFIER):
                            # Handle file announcement
                            file_info = json.loads(data[len(ANNOUNCE_IDENTIFIER):].decode('utf-8'))
                            file_name = file_info['name']
                            file_size = file_info['size']
                            total_chunks = file_info['total_chunks']
                            self.expected_chunks[file_name] = total_chunks
                            self.received_chunks[file_name] = [None] * total_chunks
                            self.retry_counts[file_name] = 0
                            message = f"File announcement received: {file_name}, Size: {file_size} bytes, Total Chunks: {total_chunks}"
                            print(Fore.BLUE + message)
                            print(Fore.BLUE + f"Expected chunks for {file_name}: {self.expected_chunks[file_name]}")
                            if self.on_receive_callback:
                                self.on_receive_callback(message, message_type="INFO")
                        elif data.startswith(FILE_IDENTIFIER):
                            # Extract file name and file data
                            parts = data[len(FILE_IDENTIFIER):].split(b':', 3)
                            if len(parts) == 4:
                                file_name = parts[0].decode('utf-8')
                                chunk_index = int(parts[1])
                                total_chunks = int(parts[2])
                                chunk_data = parts[3]

                                print(Fore.LIGHTBLUE_EX + f"Received chunk {chunk_index} for file {file_name}.")

                                if file_name not in self.received_chunks:
                                    self.received_chunks[file_name] = [None] * total_chunks
                                    print(Fore.LIGHTBLUE_EX + f"Initialized received chunks for {file_name}.")

                                if self.received_chunks[file_name][chunk_index] is None:
                                    self.received_chunks[file_name][chunk_index] = chunk_data
                                    print(Fore.LIGHTBLUE_EX + f"Stored chunk {chunk_index} for file {file_name}.")
                                    if all(self.received_chunks[file_name]):
                                        complete_data = b''.join(self.received_chunks[file_name])
                                        self.save_file(file_name, complete_data)
                                        # Reset retry count on successful receipt
                                        self.retry_counts[file_name] = 0
                        elif data.decode('utf-8').startswith("File complete:"):
                            # Handle file complete message
                            file_name = data.decode('utf-8').split(": ")[1]
                            print(Fore.GREEN + f"File complete received for {file_name}")
                            self.request_missing_chunks(file_name)
                        elif data.decode('utf-8').startswith("REQ:"):
                            # Handle missing chunk request
                            self.handle_missing_chunks(data.decode('utf-8'))
                        else:
                            message = data.decode('utf-8').strip()
                            if len(message) > 1:
                                print(Fore.GREEN + f"Received message: {message}")
                                if self.on_receive_callback:
                                    self.on_receive_callback(f"{sender_id}: {message}", message_type="RECEIVED")
                    except UnicodeDecodeError:
                        print(Fore.LIGHTBLACK_EX + f"Received non-text payload: {decoded['payload']}")
                        if self.on_receive_callback:
                            self.on_receive_callback(f"Received non-text payload: {decoded['payload']}", message_type="INFO")
                else:
                    print(Fore.LIGHTBLACK_EX + f"Received packet without text payload: {decoded}")
                    if self.on_receive_callback:
                        self.on_receive_callback(f"Received packet without text payload: {decoded}", message_type="INFO")
            else:
                print(Fore.LIGHTBLACK_EX + f"Received packet without 'decoded' field: {packet}")
                if self.on_receive_callback:
                    self.on_receive_callback(f"Received packet without 'decoded' field: {packet}", message_type="INFO")

            # Print additional details if available
            if 'from' in packet:
                message = f"From: {packet['from']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="INFO")
            if 'to' in packet:
                message = f"To: {packet['to']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="INFO")
            if 'id' in packet:
                message = f"Packet ID: {packet['id']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="INFO")
            if 'rxSnr' in packet:
                message = f"Signal-to-Noise Ratio (SNR): {packet['rxSnr']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="SNR")
            if 'rxRssi' in packet:
                message = f"Received Signal Strength Indicator (RSSI): {packet['rxRssi']}"
                print(Fore.BLUE + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="RSSI")
            if 'hopLimit' in packet:
                message = f"Hop Limit: {packet['hopLimit']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="INFO")
            if 'encrypted' in packet:
                message = f"Encrypted: {packet['encrypted']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="INFO")
            if 'fromId' in packet:
                message = f"From ID: {packet['fromId']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="INFO")
            if 'toId' in packet:
                message = f"To ID: {packet['toId']}"
                print(Fore.LIGHTBLACK_EX + message)
                if self.on_receive_callback:
                    self.on_receive_callback(message, message_type="INFO")

        except Exception as e:
            error_message = f"Error processing received packet: {e}"
            print(Fore.RED + error_message)
            if self.on_receive_callback:
                self.on_receive_callback(error_message, message_type="ERROR")

    def request_missing_chunks(self, file_name):
        """Request missing chunks from the sender"""
        if file_name in self.received_chunks:
            missing_chunks = [i for i, chunk in enumerate(self.received_chunks[file_name]) if chunk is None]
            if missing_chunks:
                if self.retry_counts[file_name] < self.retransmission_limit:
                    request_message = f"REQ:{file_name}:{','.join(map(str, missing_chunks))}"
                    self.interface.sendText(request_message, self.destination_id)
                    print(Fore.MAGENTA + f"Requesting missing chunks for {file_name}: {missing_chunks}")
                    self.retry_counts[file_name] += 1
                else:
                    print(Fore.RED + f"Max retries reached for file {file_name}. Aborting.")
            else:
                print(Fore.GREEN + f"All chunks received for {file_name}, no missing chunks.")
                # Reset retry count on successful receipt
                self.retry_counts[file_name] = 0
        else:
            print(Fore.RED + f"File {file_name} not found in received_chunks during request for missing chunks.")
            print(Fore.RED + f"Current received_chunks keys: {list(self.received_chunks.keys())}")

    def handle_missing_chunks(self, request_message):
        """Handle sending of missing chunks when requested"""
        parts = request_message.split(':')
        if len(parts) == 3 and parts[0] == "REQ":
            file_name = parts[1]
            missing_chunks = list(map(int, parts[2].split(',')))
            print(Fore.MAGENTA + f"Received request for missing chunks: {missing_chunks} for file: {file_name}")

            # Add detailed logging for file and chunk states
            print(Fore.CYAN + f"Received chunks keys: {list(self.received_chunks.keys())}")
            print(Fore.CYAN + f"Expected chunks keys: {list(self.expected_chunks.keys())}")

            if file_name in self.received_chunks:
                print(Fore.LIGHTBLUE_EX + f"File {file_name} found in received_chunks.")
                file_data = b''.join(chunk for chunk in self.received_chunks[file_name] if chunk is not None)
                print(Fore.LIGHTBLUE_EX + f"Compiled file data for {file_name}: {len(file_data)} bytes.")
                self.send_specific_chunks(file_data, file_name, missing_chunks)
            elif file_name in self.sent_chunks:
                print(Fore.LIGHTBLUE_EX + f"File {file_name} found in sent_chunks.")
                file_data = b''.join(self.sent_chunks[file_name])
                print(Fore.LIGHTBLUE_EX + f"Compiled file data for {file_name} from sent_chunks: {len(file_data)} bytes.")
                self.send_specific_chunks(file_data, file_name, missing_chunks)
            else:
                print(Fore.RED + f"File {file_name} not found in received_chunks or sent_chunks. Attempting to send from stored data.")
                # Try to send the missing chunks directly from the received message information
                file_path = os.path.join('received_files', file_name)
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as file:
                        file_data = file.read()
                        print(Fore.LIGHTBLUE_EX + f"Read file data from disk for {file_name}: {len(file_data)} bytes.")
                        self.send_specific_chunks(file_data, file_name, missing_chunks)
                else:
                    print(Fore.RED + f"No file data available for {file_name}. Cannot resend missing chunks.")

    def send_specific_chunks(self, data, file_name, chunks):
        """Send specific chunks requested by the receiver"""
        total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE

        for i in chunks:
            try:
                start = i * CHUNK_SIZE
                end = start + CHUNK_SIZE
                chunk = data[start:end]
                chunk_identifier = FILE_IDENTIFIER + f'{file_name}:{i}:{total_chunks}'.encode('utf-8') + b':'
                chunk_data = chunk_identifier + chunk

                print(Fore.YELLOW + f"Resending chunk {i+1}/{total_chunks}...")
                self.interface.sendData(
                    data=chunk_data,
                    destinationId=self.destination_id,
                    wantAck=False,  # No acknowledgment needed for chunks
                    wantResponse=False,  # No response needed for chunks
                    channelIndex=0
                )
                time.sleep(0.5)  # Add a delay between sending chunks
            except Exception as e:
                print(Fore.RED + f"Failed to resend chunk {i+1}/{total_chunks}: {str(e)}")

    # Function to save a received file
    def save_file(self, file_name, file_data):
        try:
            file_path = os.path.join('received_files', file_name)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as file:
                file.write(file_data)
            print(Fore.GREEN + f"File saved: {file_path}")
        except Exception as e:
            print(Fore.RED + f"Failed to save file: {str(e)}")

    # Function to send a text message
    def send_text_message(self, text, channel_index, destination_id=None):
        ack_event = threading.Event()  # Create an event object to wait for acknowledgment

        def callback(response):
            self.on_ack(response, ack_event)
        
        try:
            print(Fore.LIGHTBLACK_EX + "Attempting to send message...")
            sent_packet = self.interface.sendText(
                text=text,
                destinationId=destination_id if destination_id else self.destination_id,
                wantAck=True,
                wantResponse=True,
                onResponse=callback,
                channelIndex=channel_index
            )
            print(Fore.LIGHTBLACK_EX + f"Message sent with ID: {sent_packet.id}")
            ack_event.wait(timeout=self.timeout)  # Wait for acknowledgment or timeout after the set period
            if not ack_event.is_set():
                print(Fore.MAGENTA + "Acknowledgment not received within timeout period.")
        except Exception as e:
            print(Fore.RED + f"Failed to send message: {str(e)}")

    # Function to send a group message to the entire mesh
    def send_group_message(self, text, channel_index):
        try:
            print(Fore.LIGHTBLACK_EX + "Attempting to send group message...")
            sent_packet = self.interface.sendText(
                text=text,
                destinationId=BROADCAST_ADDR,
                wantAck=False,  # No acknowledgment needed for group messages
                wantResponse=False,  # No response needed for group messages
                channelIndex=channel_index
            )
            print(Fore.LIGHTBLACK_EX + f"Group message sent with ID: {sent_packet.id}")
        except Exception as e:
            print(Fore.RED + f"Failed to send group message: {str(e)}")

    def announce_file(self, file_name, file_size, total_chunks):
        """Announce the file details before sending chunks"""
        file_info = {
            "name": file_name,
            "size": file_size,
            "total_chunks": total_chunks
        }
        message = ANNOUNCE_IDENTIFIER + json.dumps(file_info).encode('utf-8')
        print(Fore.YELLOW + f"Announcing file: {file_name}, Size: {file_size} bytes, Total Chunks: {total_chunks}")
        self.send_text_message(message.decode('utf-8'), 0)  # Send as text message with acknowledgment

    # Function to send data in chunks with retransmission
    def send_data_in_chunks(self, data, file_name, progress_callback: Optional[Callable[[int, int], None]] = None, channel_index=0):
        def callback(response, event):
            self.on_ack(response, event)

        total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE
        self.announce_file(file_name, len(data), total_chunks)

        # Store chunks temporarily in memory
        self.sent_chunks[file_name] = [data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE] for i in range(total_chunks)]

        for i in range(total_chunks):
            chunk = self.sent_chunks[file_name][i]
            chunk_identifier = FILE_IDENTIFIER + f'{file_name}:{i}:{total_chunks}'.encode('utf-8') + b':'
            chunk_data = chunk_identifier + chunk

            print(Fore.LIGHTBLACK_EX + f"Sending chunk {i+1}/{total_chunks}...")
            self.interface.sendData(
                data=chunk_data,
                destinationId=self.destination_id,
                wantAck=False,  # No acknowledgment needed for chunks
                wantResponse=False,  # No response needed for chunks
                channelIndex=channel_index
            )
            time.sleep(0.5)  # Add a delay between sending chunks

            if progress_callback:
                progress_callback(i + 1, total_chunks)

        # Send "File complete" message
        self.send_text_message(f"File complete: {file_name}", channel_index)

    # Function to send IP data in chunks with retransmission
    def send_ip_data_in_chunks(self, url, destination_id, progress_callback: Optional[Callable[[int, int], None]] = None, channel_index=0):
        def callback(response, event):
            self.on_ack(response, event)
            
        try:
            response = requests.get(url)
            data = response.content
            file_name = url.split("/")[-1]  # Use the last part of the URL as the file name
            total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE

            # Store chunks temporarily in memory
            self.sent_chunks[file_name] = [data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE] for i in range(total_chunks)]

            for i in range(total_chunks):
                chunk = self.sent_chunks[file_name][i]
                chunk_identifier = IPDATA_IDENTIFIER + f'{file_name}:{i}:{total_chunks}'.encode('utf-8') + b':'
                chunk_data = chunk_identifier + chunk

                print(Fore.LIGHTBLACK_EX + f"Sending chunk {i+1}/{total_chunks}...")
                self.interface.sendData(
                    data=chunk_data,
                    destinationId=destination_id,
                    wantAck=False,  # No acknowledgment needed for chunks
                    wantResponse=False,  # No response needed for chunks
                    channelIndex=channel_index
                )
                time.sleep(0.5)  # Add a delay between sending chunks
                
                if progress_callback:
                    progress_callback(i + 1, total_chunks)
                
            # Send "IP data complete" message
            self.send_text_message(f"IP data complete: {file_name}", channel_index)
        except Exception as e:
            print(Fore.RED + f"Failed to send IP data: {str(e)}")

    def request_ip_data(self, url, destination_id, channel_index=0):
        request_message = f'IPREQ:{url}'
        self.send_text_message(request_message, channel_index, destination_id)

    def send_data(self, data, channel_index):
        ack_event = threading.Event()  # Create an event object to wait for acknowledgment

        def callback(response):
            self.on_ack(response, ack_event)
        
        try:
            print(Fore.LIGHTBLACK_EX + "Attempting to send data...")
            sent_packet = self.interface.sendData(
                data=data,
                destinationId=self.destination_id,
                wantAck=True,
                wantResponse=True,
                onResponse=callback,
                channelIndex=channel_index
            )
            print(Fore.LIGHTBLACK_EX + f"Data sent with ID: {sent_packet.id}")
            ack_event.wait(timeout=self.timeout)  # Wait for acknowledgment or timeout after the set period
            if not ack_event.is_set():
                print(Fore.MAGENTA + "Acknowledgment not received within timeout period.")
        except Exception as e:
            print(Fore.RED + f"Failed to send data: {str(e)}")

    # Function to show nodes
    def show_nodes(self, include_self: bool=True) -> list:
        """Return a list of nodes in the mesh"""
        def format_float(value, precision=2, unit="") -> Optional[str]:
            """Format a float value with precision."""
            return f"{value:.{precision}f}{unit}" if value else None

        def get_lh(ts) -> Optional[str]:
            """Format last heard"""
            return (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else None
            )

        def get_time_ago(ts) -> Optional[str]:
            """Format how long ago have we heard from this node (aka timeago)."""
            return (
                timeago.format(datetime.fromtimestamp(ts), datetime.now())
                if ts
                else None
            )

        rows: list[dict[str, any]] = []
        if self.interface.nodesByNum:
            logging.debug(f"self.interface.nodes:{self.interface.nodes}")
            for node in self.interface.nodesByNum.values():
                if not include_self and node["num"] == self.interface.localNode.nodeNum:
                    continue

                presumptive_id = f"!{node['num']:08x}"
                row = {"N": 0, "User": f"Meshtastic {presumptive_id[-4:]}", "ID": presumptive_id}

                user = node.get("user")
                if user:
                    row.update(
                        {
                            "User": user.get("longName", "N/A"),
                            "AKA": user.get("shortName", "N/A"),
                            "ID": user["id"],
                            "Hardware": user.get("hwModel", "UNSET")
                        }
                    )

                pos = node.get("position")
                if pos:
                    row.update(
                        {
                            "Latitude": format_float(pos.get("latitude"), 4, "°"),
                            "Longitude": format_float(pos.get("longitude"), 4, "°"),
                            "Altitude": format_float(pos.get("altitude"), 0, " m"),
                        }
                    )

                metrics = node.get("deviceMetrics")
                if metrics:
                    battery_level = metrics.get("batteryLevel")
                    if battery_level is not None:
                        if battery_level == 0:
                            battery_string = "Powered"
                        else:
                            battery_string = str(battery_level) + "%"
                        row.update({"Battery": battery_string})
                    row.update(
                        {
                            "Channel util.": format_float(
                                metrics.get("channelUtilization"), 2, "%"
                            ),
                            "Tx air util.": format_float(
                                metrics.get("airUtilTx"), 2, "%"
                            ),
                        }
                    )

                row.update(
                    {
                        "SNR": format_float(node.get("snr"), 2, " dB"),
                        "Hops Away": node.get("hopsAway", "0/unknown"),
                        "Channel": node.get("channel", 0),
                        "LastHeard": get_lh(node.get("lastHeard")),
                        "Since": get_time_ago(node.get("lastHeard")),
                    }
                )

                rows.append(row)

        rows.sort(key=lambda r: r.get("LastHeard") or "0000", reverse=True)
        for i, row in enumerate(rows):
            row["N"] = i + 1

        return rows

    def get_channels(self):
        """Get the current channel settings from the node."""
        try:
            channels = []
            for channel in self.interface.localNode.channels:
                if channel.role != channel_pb2.Channel.Role.DISABLED:
                    channels.append({
                        'Index': channel.index,
                        'Role': channel_pb2.Channel.Role.Name(channel.role),
                        'Name': channel.settings.name,
                        'PSK': base64.b64encode(channel.settings.psk).decode('utf-8'),  # Encode to base64
                    })
            return channels
        except Exception as e:
            print(Fore.RED + f"Failed to get channels: {str(e)}")
            return None

    def set_psk(self, index, psk):
        """Set the PSK for a given channel index."""
        try:
            if index < len(self.interface.localNode.channels):
                self.interface.localNode.channels[index].settings.psk = psk
                self.interface.localNode.writeChannel(index)
                print(Fore.GREEN + f"PSK for channel {index} set successfully.")
            else:
                print(Fore.RED + f"Invalid channel index: {index}")
        except Exception as e:
            print(Fore.RED + f"Failed to set PSK: {str(e)}")

    def add_channel(self, name):
        disabled_channel = self.interface.localNode.getDisabledChannel()
        if not disabled_channel:
            raise ValueError("No available disabled channel to add a new one.")
        try:
            disabled_channel.role = channel_pb2.Channel.Role.SECONDARY
            disabled_channel.settings.name = name
            disabled_channel.settings.psk = self.interface.localNode.channels[0].settings.psk  # Using the same PSK as primary for simplicity
            self.interface.localNode.writeChannel(disabled_channel.index)
        except Exception as e:
            print(Fore.RED + f"Failed to add channel: {str(e)}")
    
    def get_device_ip(self):
        """Get the device IP address"""
        if not self.interface:
            return None
        node_num = self.interface.myInfo.my_node_num
        ip_address = f"10.115.{(node_num >> 8) & 0xff}.{node_num & 0xff}"
        return ip_address
    
    # Tunnel-related methods
    if platform.system() == "Linux":
        def start_tunnel_client(self):
            if self.tunnel:
                self.tunnel.close()
            self.tunnel = Tunnel(self.interface)
            threading.Thread(target=self.tunnel._tunReader, daemon=True).start()
            logging.info("Tunnel client started.")
        
        def start_tunnel_gateway(self):
            if self.tunnel:
                self.tunnel.close()
            self.tunnel = Tunnel(self.interface)
            threading.Thread(target=self.tunnel._tunReader, daemon=True).start()
            logging.info("Tunnel gateway started.")
        
        def close_tunnel(self):
            if self.tunnel:
                self.tunnel.close()
                self.tunnel = None
                logging.info("Tunnel closed.")

        def start_browser(self):
            if self.tunnel:
                self.tunnel.close()
            self.tunnel = Tunnel(self.interface)
            self.tunnel.start_browser()
    
    def send_tunnel_packet(self, dest_ip, message):
        """Send a packet through the tunnel"""
        if not self.tunnel:
            print("Tunnel is not initialized.")
            return

        try:
            dest_addr = self.tunnel._ipToNodeId(dest_ip)
            if dest_addr:
                packet = message.encode('utf-8')
                self.tunnel.sendPacket(dest_ip, packet)
                print(f"Packet sent to {dest_ip}")
            else:
                print(f"Invalid destination IP: {dest_ip}")
        except Exception as e:
            print(f"Failed to send packet: {e}")
            
    def sendTraceRoute(self, dest: Union[int, str], hopLimit: int, channelIndex: int=0):
        """Send the trace route"""
        r = mesh_pb2.RouteDiscovery()
        self.interface.sendData(
            r.SerializeToString(),
            destinationId=dest,
            portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
            wantResponse=True,
            onResponse=self.onResponseTraceRoute,
            channelIndex=channelIndex,
        )
        # extend timeout based on number of nodes, limit by configured hopLimit
        waitFactor = min(len(self.interface.nodes) - 1 if self.interface.nodes else 0, hopLimit)
        self.waitForTraceRoute(waitFactor)

    def onResponseTraceRoute(self, p: dict):
        """on response for trace route"""
        routeDiscovery = mesh_pb2.RouteDiscovery()
        routeDiscovery.ParseFromString(p["decoded"]["payload"])
        asDict = google.protobuf.json_format.MessageToDict(routeDiscovery)

        print("Route traced:")
        routeStr = self._nodeNumToId(p["to"])
        if "route" in asDict:
            for nodeNum in asDict["route"]:
                routeStr += " --> " + self._nodeNumToId(nodeNum)
        routeStr += " --> " + self._nodeNumToId(p["from"])
        print(routeStr)

        self._acknowledgment.receivedTraceRoute = True

    def waitForTraceRoute(self, waitFactor):
        """Wait for trace route response"""
        timeout = self.timeout + waitFactor * 5
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._acknowledgment.receivedTraceRoute:
                return True
            time.sleep(0.5)
        print(Fore.MAGENTA + "Trace route response not received within timeout period.")
        return False

    def _nodeNumToId(self, nodeNum):
        """Convert node number to node ID"""
        for node in self.interface.nodesByNum.values():
            if node["num"] == nodeNum:
                return node["user"]["id"]
        return f"!{nodeNum:08x}"
    
    def set_timeout(self, timeout):
        self.timeout = timeout
    
    # Flask-related methods
    def start_flask_server(self):
        if not self.flask_server_running:
            threading.Thread(target=self.run_flask_server, daemon=True).start()
            self.flask_server_running = True
            print(Fore.GREEN + "Flask server started.")
        else:
            print(Fore.YELLOW + "Flask server is already running.")

    def stop_flask_server(self):
        if self.flask_server_running:
            # Implement logic to stop the Flask server gracefully
            self.flask_server_running = False
            print(Fore.RED + "Flask server stopped.")
        else:
            print(Fore.YELLOW + "Flask server is not running.")

    def run_flask_server(self):
        from Flask.flask_server import app, socketio, start_heartbeat_monitor
        app.config['chat_app'] = self
        start_heartbeat_monitor(self)
        socketio.run(app, host='0.0.0.0', port=5003)

    def forward_to_subscribers(self, sender_id, message, packet):
        from Flask.flask_server import socketio  # Import socketio here to ensure it's available
        for subscriber_id, info in self.subscribers.items():
            try:
                payload = {'sender_id': sender_id, 'message': message}
                if info["verbose"]:
                    payload.update({
                        "from": packet.get("from"),
                        "to": packet.get("to"),
                        "id": packet.get("id"),
                        "rxSnr": packet.get("rxSnr"),
                        "rxRssi": packet.get("rxRssi"),
                        "hopLimit": packet.get("hopLimit"),
                        "encrypted": packet.get("encrypted"),
                        "fromId": packet.get("fromId"),
                        "toId": packet.get("toId"),
                    })
                sid = info["sid"]
                socketio.emit('message', payload, room=sid)
                print(Fore.LIGHTBLACK_EX + f"Forwarded message to {subscriber_id}: {message}")
            except Exception as e:
                print(Fore.RED + f"Failed to forward message to {subscriber_id}: {str(e)}")
    
    def forward_ip_data_to_clients(self, ip_data):
        from Flask.flask_server import socketio  # Import socketio here to ensure it's available
        for subscriber_id, info in self.subscribers.items():
            try:
                payload = {'content': ip_data}
                sid = info["sid"]
                socketio.emit('ip_data', payload, room=sid)
                print(Fore.LIGHTBLACK_EX + f"Forwarded IP data to {subscriber_id}: {ip_data[:50]}...")
            except Exception as e:
                print(Fore.RED + f"Failed to forward IP data to {subscriber_id}: {str(e)}")
            
    # Main loop to switch between sender and receiver modes
    def run(self):
        try:
            while True:
                choice = input(Fore.CYAN + "Enter 'm' to send a message, 'f' to send a file, or 'exit' to quit: ")
                if choice.lower() == 'exit':
                    break
                elif choice.lower() == 'm':
                    text = input(Fore.CYAN + "Enter the message to send: ")
                    print(Fore.YELLOW + f"Sending message: {text}")  # Send message text in yellow
                    self.send_text_message(text, channel_index=0)
                elif choice.lower() == 'f':
                    file_path = input(Fore.CYAN + "Enter the file path to send: ")
                    try:
                        with open(file_path, 'rb') as file:
                            file_data = file.read()
                            file_name = os.path.basename(file_path)
                            print(Fore.YELLOW + f"Sending file: {file_name}")  # Send file name in yellow
                            self.send_data_in_chunks(file_data, file_name, channel_index=0)
                    except Exception as e:
                        print(Fore.RED + f"Failed to read file: {str(e)}")
                else:
                    print(Fore.MAGENTA + "Invalid choice. Please enter 'm', 'f', or 'exit'.")
        except KeyboardInterrupt:
            print(Fore.MAGENTA + "\nExiting the program.")
