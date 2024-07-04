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
from tabulate import tabulate
import base64
import google.protobuf.json_format
import platform

# Initialize colorama
init(autoreset=True)

if platform.system() == "Linux":
    from meshtastic.tunnel import Tunnel  # Import the Tunnel class

# Enable logging but set to ERROR level to suppress debug/info messages
logging.basicConfig(level=logging.ERROR)

FILE_IDENTIFIER = b'FILEDATA:'
ANNOUNCE_IDENTIFIER = b'FILEINFO:'
CHUNK_SIZE = 100  # Chunk size in bytes
BROADCAST_ADDR = "^all"

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
                        if data.startswith(ANNOUNCE_IDENTIFIER):
                            # Handle file announcement
                            file_info = json.loads(data[len(ANNOUNCE_IDENTIFIER):].decode('utf-8'))
                            file_name = file_info['name']
                            file_size = file_info['size']
                            total_chunks = file_info['total_chunks']
                            self.expected_chunks[file_name] = total_chunks
                            self.received_chunks[file_name] = [None] * total_chunks
                            message = f"File announcement received: {file_name}, Size: {file_size} bytes, Total Chunks: {total_chunks}"
                            print(Fore.BLUE + message)
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

                                if file_name not in self.received_chunks:
                                    self.received_chunks[file_name] = [None] * total_chunks

                                if self.received_chunks[file_name][chunk_index] is None:
                                    self.received_chunks[file_name][chunk_index] = chunk_data
                                    self.acknowledge_chunk(file_name, chunk_index, sender_id)  # Pass sender ID

                                    if all(self.received_chunks[file_name]):
                                        complete_data = b''.join(self.received_chunks[file_name])
                                        self.save_file(file_name, complete_data)
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
                
    def acknowledge_chunk(self, file_name, chunk_index, sender_id):
       """Send an acknowledgment for a received chunk to the sender."""
       ack_message = f"ACK:{file_name}:{chunk_index}"
       self.interface.sendText(ack_message, sender_id)
       print(Fore.GREEN + f"Acknowledgment sent for chunk {chunk_index} of {file_name} to {sender_id}")

    def request_missing_chunks(self, file_name):
        """Request missing chunks from the sender"""
        missing_chunks = [i for i, chunk in enumerate(self.received_chunks[file_name]) if chunk is None]
        if missing_chunks:
            request_message = f"REQ:{file_name}:{','.join(map(str, missing_chunks))}"
            self.interface.sendText(request_message, self.destination_id)
            print(Fore.MAGENTA + f"Requesting missing chunks for {file_name}: {missing_chunks}")

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
        self.send_data(message, 0)

    # Function to send data in chunks with retransmission
    def send_data_in_chunks(self, data, file_name, progress_callback: Optional[Callable[[int, int], None]] = None, channel_index=0):
        def callback(response, event):
            self.on_ack(response, event)

        total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE
        self.announce_file(file_name, len(data), total_chunks)

        for i in range(total_chunks):
            start = i * CHUNK_SIZE
            end = start + CHUNK_SIZE
            chunk = data[start:end]
            chunk_identifier = FILE_IDENTIFIER + f'{file_name}:{i}:{total_chunks}'.encode('utf-8') + b':'
            chunk_data = chunk_identifier + chunk

            retries = 0
            while retries < self.retransmission_limit:
                ack_event = threading.Event()  # Create an event object to wait for acknowledgment

                print(Fore.LIGHTBLACK_EX + f"Sending chunk {i+1}/{total_chunks}, attempt {retries + 1}...")
                sent_packet = self.interface.sendData(
                    data=chunk_data,
                    destinationId=self.destination_id,
                    wantAck=True,
                    wantResponse=True,
                    onResponse=lambda response: callback(response, ack_event),
                    channelIndex=channel_index
                )
                print(Fore.LIGHTBLACK_EX + f"Chunk {i+1}/{total_chunks} sent with ID: {sent_packet.id}")
                ack_event.wait(timeout=self.timeout)  # Wait for acknowledgment or timeout after the set period

                if ack_event.is_set():
                    self.acknowledged_chunks.add((file_name, i))
                    if progress_callback:
                        progress_callback(i + 1, total_chunks)
                    break
                else:
                    print(Fore.MAGENTA + f"Acknowledgment not received for chunk {i+1}/{total_chunks} within timeout period.")
                    retries += 1
                    time.sleep(2)  # Add a small delay before retrying

            if retries == self.retransmission_limit:
                print(Fore.RED + f"Failed to send chunk {i+1}/{total_chunks} after {self.retransmission_limit} attempts. Aborting.")
                return  # Abort if the maximum number of retransmissions is reached

    # Function to send data
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
