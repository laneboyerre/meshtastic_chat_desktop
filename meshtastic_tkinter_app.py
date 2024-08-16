import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import threading
import json
import os
import base64
import webview
from Class.meshtastic_chat_app import MeshtasticChatApp  # Import your existing class
import platform
import serial.tools.list_ports
 
from Class.friends_modules.FriendsManager import FriendsManager
from Class.friends_modules.PickleFriendInterfaceImpl import PickleFriendInterface
from Class.friends_modules.friend import Friend

CHUNK_SIZE = 100  # Define CHUNK_SIZE here
STYLE = 'default'  # Set the style to be used for the ttk widgets

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self)
        canvas.config(width=975, height=600)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        style = ttk.Style()
        style.theme_use(STYLE)

class MeshtasticTkinterApp:
    def __init__(self, master):
        self.master = master
        self.master.option_add("*Background", "white")
        self.master.option_add("*Foreground", "black")
        self.master.option_add("*Entry*background", "white")
        self.master.title("Meshtastic Chat App")

        # Create a menu bar
        self.menu_bar = tk.Menu(master)
        master.config(menu=self.menu_bar)

        # Create a File menu
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=self.file_menu)
        if platform.system() == "Linux":
            from meshtastic.tunnel import Tunnel  # Import the Tunnel class
            # Linux Only Menu
            self.file_menu.add_command(label="Tunnel Client", command=self.open_tunnel_client)
            self.file_menu.add_command(label="Tunnel Gateway", command=self.open_tunnel_gateway)
            self.file_menu.add_command(label="Browser", command=self.open_browser)
        # Normal Windows Menu    
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=master.quit)
        
        self.right_click_menu = tk.Menu(root, tearoff = 0) 
        self.right_click_menu.add_command(label ="Add to Friends", command=self.add_friend_right_click) 
        
        self.FriendManager = FriendsManager(PickleFriendInterface())
        
        # Create a View menu
        self.view_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="View", menu=self.view_menu)
        self.view_menu.add_separator()
        
        # Variables
        self.device_path = tk.StringVar()
        self.destination_id = tk.StringVar()
        self.timeout = tk.IntVar(value=30)
        self.retransmission_limit = tk.IntVar(value=3)
        self.destination_id.set("!fa6a4660")  # Default destination ID
        

        # Set up the scrollable frame
        self.scrollable_frame = ScrollableFrame(self.master)
        self.scrollable_frame.pack(fill="both", expand=True)
        self.frame = self.scrollable_frame.scrollable_frame

        # Set up the UI elements
        self.setup_ui()

        self.chat_app = None  # Initialize later after setting the device path

        
    
    def setup_ui(self):
        # Device Path
        ttk.Label(self.frame, text="Device Path:").grid(row=0, column=0, padx=10, pady=5)
        options = [port.device for port in serial.tools.list_ports.comports()]  # Get a list of paths
        dropdown = ttk.Combobox(self.frame, textvariable=self.device_path)
        dropdown['values'] = options
        dropdown.set('')  # Set default value
        dropdown.grid(row=0, column=1, padx=10, pady=5)
        ttk.Button(self.frame, text="Connect", command=self.connect_device).grid(row=0, column=2, padx=10, pady=5)

        # Timeout
        ttk.Label(self.frame, text="Timeout (s):").grid(row=1, column=0, padx=10, pady=5)
        ttk.Entry(self.frame, textvariable=self.timeout).grid(row=1, column=1, padx=10, pady=5)

        # Retransmission Limit
        ttk.Label(self.frame, text="Retransmission Limit:").grid(row=2, column=0, padx=10, pady=5)
        ttk.Entry(self.frame, textvariable=self.retransmission_limit).grid(row=2, column=1, padx=10, pady=5)

        # Friends/Address List
        self.friends_frame = ttk.LabelFrame(self.frame, text="Friends/Addresses")
        self.friends_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        self.friends_frame.grid_rowconfigure(0, weight=1)
        self.friends_frame.grid_columnconfigure(0, weight=1)

        self.friends_listbox = tk.Listbox(self.friends_frame)
        self.friends_listbox.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.friends_listbox.bind('<<ListboxSelect>>', self.on_friend_select)

        self.add_friend_button = ttk.Button(self.friends_frame, text="Add Friend", command=self.add_friend)
        self.add_friend_button.grid(row=1, column=0, padx=5, pady=5)

        self.remove_friend_button = ttk.Button(self.friends_frame, text="Remove Friend", command=self.remove_friend)
        self.remove_friend_button.grid(row=2, column=0, padx=5, pady=5)
        
        # Add Trace Route Button
        self.trace_route_button = ttk.Button(self.friends_frame, text="Trace Route", command=self.trace_route)
        self.trace_route_button.grid(row=3, column=0, padx=5, pady=5)
        
        # Output Frame
        self.output_frame = ttk.LabelFrame(self.frame, text="Radio Output")
        self.output_frame.grid(row=3, column=1, padx=10, pady=10, sticky="nsew", columnspan=2)

        self.output_text = tk.Text(self.output_frame, height=10, state='disabled', bg='black', fg='white', wrap='word')
        self.output_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.output_frame.grid_rowconfigure(0, weight=1)
        self.output_frame.grid_columnconfigure(0, weight=1)

        # Add tags for different text colors
        self.output_text.tag_configure("INFO", foreground="white")
        self.output_text.tag_configure("SUCCESS", foreground="green")
        self.output_text.tag_configure("WARNING", foreground="magenta")
        self.output_text.tag_configure("ERROR", foreground="red")
        self.output_text.tag_configure("SNR", foreground="lightblue")
        self.output_text.tag_configure("RSSI", foreground="blue")

        # Message History
        self.history_frame = ttk.LabelFrame(self.frame, text="Message History")
        self.history_frame.grid(row=4, column=0, padx=10, pady=10, sticky="nsew")

        self.history_text = tk.Text(self.history_frame, height=10, width=50, state='disabled')
        self.history_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.history_frame.grid_rowconfigure(0, weight=1)
        self.history_frame.grid_columnconfigure(0, weight=1)

        # Mesh Section
        self.mesh_frame = ttk.LabelFrame(self.frame, text="Mesh")
        self.mesh_frame.grid(row=4, column=1, padx=10, pady=10, sticky="nsew", columnspan=2)
        self.mesh_frame.grid_rowconfigure(0, weight=1)
        self.mesh_frame.grid_columnconfigure(0, weight=1)

        # Canvas for scrolling
        self.mesh_canvas = tk.Canvas(self.mesh_frame)
        self.mesh_canvas.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Scrollbars
        self.mesh_scrollbar_y = ttk.Scrollbar(self.mesh_frame, orient="vertical", command=self.mesh_canvas.yview)
        self.mesh_scrollbar_y.grid(row=0, column=1, sticky="ns")
        self.mesh_scrollbar_x = ttk.Scrollbar(self.mesh_frame, orient="horizontal", command=self.mesh_canvas.xview)
        self.mesh_scrollbar_x.grid(row=1, column=0, sticky="ew")

        # Treeview for displaying nodes
        columns = ("N", "User", "ID", "AKA", "Hardware", "Latitude", "Longitude", "Battery", "Channel util.", "Tx air util.", "SNR", "Hops Away", "LastHeard", "Since")
        self.mesh_tree = ttk.Treeview(self.mesh_canvas, columns=columns, show='headings')
        self.mesh_tree.grid(row=0, column=0, sticky="nsew")
        
        if platform.system() == "Darwin":
            self.mesh_tree.bind("<Button-2>", self.right_click_popup) 
        else:
            self.mesh_tree.bind("<Button-3>", self.right_click_popup) 

        # Define column headings and set default widths
        column_widths = {
            "N": 30, "User": 120, "ID": 150, "AKA": 70, "Hardware": 100,
            "Latitude": 90, "Longitude": 90, "Battery": 70, "Channel util.": 100,
            "Tx air util.": 100, "SNR": 70, "Hops Away": 70, "LastHeard": 150, "Since": 100
        }
        
        for col in columns:
            self.mesh_tree.heading(col, text=col)
            self.mesh_tree.column(col, width=column_widths.get(col, 100), stretch=tk.NO)

        self.mesh_canvas.create_window((0, 0), window=self.mesh_tree, anchor='nw')
        self.mesh_tree.configure(yscrollcommand=self.mesh_scrollbar_y.set, xscrollcommand=self.mesh_scrollbar_x.set)

        self.mesh_tree.bind("<Configure>", lambda e: self.mesh_canvas.configure(scrollregion=self.mesh_canvas.bbox("all")))

        self.scan_button = ttk.Button(self.mesh_frame, text="Scan", command=self.scan_mesh)
        self.scan_button.grid(row=2, column=0, padx=5, pady=5)

        # Entry Frame for Messages
        self.entry_frame = ttk.Frame(self.frame)
        self.entry_frame.grid(row=5, column=0, padx=10, pady=10, sticky="nsew", columnspan=3)

        self.message_entry = ttk.Entry(self.entry_frame, width=50)
        self.message_entry.grid(row=0, column=0, padx=5, pady=5)

        self.send_button = ttk.Button(self.entry_frame, text="Send Message", command=self.send_message)
        self.send_button.grid(row=0, column=1, padx=5, pady=5)

        self.group_message_button = ttk.Button(self.entry_frame, text="Send Group Message", command=self.send_group_message)
        self.group_message_button.grid(row=0, column=2, padx=5, pady=5)

        self.file_button = ttk.Button(self.entry_frame, text="Send File", command=self.send_file)
        self.file_button.grid(row=0, column=3, padx=5, pady=5)

        # Progress Bar
        self.progress_frame = ttk.Frame(self.frame)
        self.progress_frame.grid(row=6, column=0, padx=10, pady=10, sticky="nsew", columnspan=3)

        self.progress_label = ttk.Label(self.progress_frame, text="Progress:")
        self.progress_label.grid(row=0, column=0, padx=5, pady=5)

        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", length=400, mode="determinate")
        self.progress_bar.grid(row=0, column=1, padx=5, pady=5)

        # Channel Settings
        self.channel_frame = ttk.LabelFrame(self.frame, text="Channel Settings")
        self.channel_frame.grid(row=7, column=0, padx=10, pady=10, sticky="nsew", columnspan=3)

        self.channel_text = tk.Text(self.channel_frame, height=10, state='disabled')
        self.channel_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.channel_frame.grid_rowconfigure(0, weight=1)
        self.channel_frame.grid_columnconfigure(0, weight=1)

        self.channel_button = ttk.Button(self.channel_frame, text="Get Channels", command=self.get_channels)
        self.channel_button.grid(row=1, column=0, padx=5, pady=5)

        self.psk_label = ttk.Label(self.channel_frame, text="Set PSK Key:")
        self.psk_label.grid(row=2, column=0, padx=5, pady=5)

        self.psk_base64_entry = ttk.Entry(self.channel_frame)
        self.psk_base64_entry.grid(row=2, column=1, padx=5, pady=5)

        self.channel_index_label = ttk.Label(self.channel_frame, text="Channel Index:")
        self.channel_index_label.grid(row=3, column=0, padx=5, pady=5)
        self.channel_index_entry = ttk.Entry(self.channel_frame)
        self.channel_index_entry.grid(row=3, column=1, padx=5, pady=5)

        self.psk_button = ttk.Button(self.channel_frame, text="Set PSK", command=self.set_psk)
        self.psk_button.grid(row=4, column=1, padx=5, pady=5)

        # Add a new entry in the setup_ui method for Channel selection
        self.message_channel_label = ttk.Label(self.entry_frame, text="Message Channel Index:")
        self.message_channel_label.grid(row=1, column=0, padx=5, pady=5)
        self.message_channel_entry = ttk.Entry(self.entry_frame)
        self.message_channel_entry.grid(row=1, column=1, padx=5, pady=5)

        self.file_channel_label = ttk.Label(self.entry_frame, text="File Channel Index:")
        self.file_channel_label.grid(row=2, column=0, padx=5, pady=5)
        self.file_channel_entry = ttk.Entry(self.entry_frame)
        self.file_channel_entry.grid(row=2, column=1, padx=5, pady=5)

        # Add Channel Name Entry and Button
        self.new_channel_label = ttk.Label(self.channel_frame, text="New Channel Name:")
        self.new_channel_label.grid(row=5, column=0, padx=5, pady=5)
        self.new_channel_entry = ttk.Entry(self.channel_frame)
        self.new_channel_entry.grid(row=5, column=1, padx=5, pady=5)

        self.add_channel_button = ttk.Button(self.channel_frame, text="Add Channel", command=self.add_channel)
        self.add_channel_button.grid(row=6, column=1, padx=5, pady=5)

        # Flask Server Section
        self.server_status_label = ttk.Label(self.frame, text="Server Status: Inactive")
        self.server_status_label.grid(row=8, column=0, padx=10, pady=5)

        self.server_button = ttk.Button(self.frame, text="Run Server", command=self.toggle_server)
        self.server_button.grid(row=8, column=1, padx=10, pady=5)
        
        self.update_friends_list()

    def connect_device(self):
        device_path = self.device_path.get()
        if device_path:
            if self.chat_app:
                self.chat_app.interface.close()
            self.chat_app = MeshtasticChatApp(
                dev_path=device_path, 
                destination_id=self.destination_id.get(),
                on_receive_callback=self.update_output,
                timeout=self.timeout.get(),
                retransmission_limit=self.retransmission_limit.get()
            )
            self.update_output("Connected to the Meshtastic device successfully.")

    def on_friend_select(self, event):
        if not self.friends_listbox.curselection():
            return
        selected_friend = self.friends_listbox.get(self.friends_listbox.curselection())
        self.destination_id.set(selected_friend)
        if self.chat_app:
            self.chat_app.set_destination_id(selected_friend)
        self.update_output(f"Destination ID set to {selected_friend}")

    def add_friend(self):
        radio_id = simpledialog.askstring("Add Friend", "Enter friend address:")
        if radio_id:
            self.FriendManager.add_friend(Friend(radio_id))
            self.update_friends_list()

    def remove_friend(self):
        selected_friend = self.friends_listbox.get(self.friends_listbox.curselection())
        if selected_friend:
            self.FriendManager.remove_friend(selected_friend)
            self.update_friends_list()

    def update_friends_list(self):
        self.friends_listbox.delete(0, tk.END)
        for friend, metadata in self.FriendManager.friends_dictionary.items():
            self.friends_listbox.insert(tk.END, friend)

    def send_message(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        
        self.chat_app.set_timeout(self.timeout.get())  # Update timeout before sending
        message = self.message_entry.get()
        if message:
            try:
                channel_index = int(self.message_channel_entry.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid channel index")
                return
            threading.Thread(target=self.chat_app.send_text_message, args=(message, channel_index)).start()

            self.update_history(f"Me: {message}")
            self.message_entry.delete(0, tk.END)

    def send_group_message(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        
        self.chat_app.set_timeout(self.timeout.get())  # Update timeout before sending
        message = self.message_entry.get()
        if message:
            try:
                channel_index = int(self.message_channel_entry.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid channel index")
                return
            self.chat_app.send_group_message(message, channel_index)
            self.update_history(f"Me: {message} (Group)")
            self.message_entry.delete(0, tk.END)

    def send_file(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        
        file_path = filedialog.askopenfilename()
        if file_path:
            try:
                channel_index = int(self.file_channel_entry.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid channel index")
                return
            threading.Thread(target=self.send_file_in_chunks, args=(file_path, channel_index)).start()

    def send_file_in_chunks(self, file_path, channel_index):
        self.chat_app.set_timeout(self.timeout.get())  # Update timeout before sending
        
        def progress_callback(current_chunk, total_chunks):
            self.progress_bar['maximum'] = total_chunks
            self.progress_bar['value'] = current_chunk
            self.master.update_idletasks()

        try:
            with open(file_path, 'rb') as file:
                file_data = file.read()
                file_name = os.path.basename(file_path)
                self.chat_app.send_data_in_chunks(file_data, file_name, progress_callback, channel_index)
                self.update_history(f"Me: Sent filefrom Class.friends_modules.friend import Friend {file_name}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to send file: {str(e)}")

    def scan_mesh(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return

        nodes = self.chat_app.show_nodes()
        self.mesh_tree.delete(*self.mesh_tree.get_children())  # Clear existing nodes in the tree

        for node in nodes:
            values = [node.get(col) for col in self.mesh_tree["columns"]]
            self.mesh_tree.insert("", tk.END, values=values)
        
        self.highlight_snr_column()  # Optional: Add highlighting for SNR column

        # Adjust the Treeview height if necessary to accommodate all nodes
        total_nodes = len(nodes)
        if total_nodes > 10:
            treeview_height = total_nodes
        else:
            treeview_height = 10

        self.mesh_tree.configure(height=treeview_height)

    def highlight_snr_column(self):
        all_snr_values = []
        for row_id in self.mesh_tree.get_children():
            snr_value = self.mesh_tree.item(row_id)["values"][10]
            if snr_value and isinstance(snr_value, str) and snr_value.endswith(" dB"):
                try:
                    all_snr_values.append(float(snr_value[:-3]))
                except ValueError:
                    continue

        if not all_snr_values:
            return

        max_snr = max(all_snr_values)
        min_snr = min(all_snr_values)
        snr_range = max_snr - min_snr

        for row_id in self.mesh_tree.get_children():
            snr_value = self.mesh_tree.item(row_id)["values"][10]
            if snr_value and isinstance(snr_value, str) and snr_value.endswith(" dB"):
                try:
                    snr = float(snr_value[:-3])
                    color_intensity = int(255 * (snr - min_snr) / snr_range) if snr_range != 0 else 0
                    color = f'#{color_intensity:02x}ff{255 - color_intensity:02x}'  # Gradient from red to green
                    self.mesh_tree.tag_configure(f'snr_{row_id}', background=color)
                    self.mesh_tree.item(row_id, tags=(f'snr_{row_id}',))
                except ValueError:
                    continue

    def get_channels(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        
        channels_info = self.chat_app.get_channels()
        if channels_info:
            self.channel_text.configure(state='normal')
            self.channel_text.delete(1.0, tk.END)
            for channel in channels_info:
                self.channel_text.insert(tk.END, f"Index: {channel['Index']}, Role: {channel['Role']}, Name: {channel['Name']}, PSK: {channel['PSK']}\n")
            self.channel_text.configure(state='disabled')

    def set_psk(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        
        psk_base64 = self.psk_base64_entry.get()
        try:
            index = int(self.channel_index_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid channel index")
            return
        
        try:
            psk_bytes = base64.b64decode(psk_base64)
            self.chat_app.set_psk(index, psk_bytes)
            self.update_output(f"PSK for channel {index} set successfully.")
            messagebox.showinfo("Success", f"Successfully set PSK for channel index: {index}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set PSK: {str(e)}")

    def add_channel(self):
        name = self.new_channel_entry.get()
        if not name:
            messagebox.showerror("Error", "Channel name cannot be empty")
            return
        try:
            self.chat_app.add_channel(name)
            self.update_output(f"Channel '{name}' added successfully.")
            messagebox.showinfo("Success", f"Channel '{name}' added successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add channel: {str(e)}")
    
    def trace_route(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        
        dest_id = self.destination_id.get()
        try:
            hop_limit = int(simpledialog.askinteger("Trace Route", "Enter hop limit:"))
        except ValueError:
            messagebox.showerror("Error", "Invalid hop limit")
            return

        self.chat_app.sendTraceRoute(dest=dest_id, hopLimit=hop_limit)
            
    def open_tunnel_client(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        tunnel_client_window = tk.Toplevel(self.master)
        tunnel_client_window.title("Tunnel Client")

        ip_address = self.chat_app.get_device_ip()
        if ip_address:
            message = f"Tunnel Client Setup\nDevice IP Address: {ip_address}"
        else:
            message = "Tunnel Client Setup\nDevice IP Address: Not available"

        tk.Label(tunnel_client_window, text=message).pack(padx=10, pady=10)

        tk.Label(tunnel_client_window, text="Destination IP:").pack(padx=10, pady=5)
        dest_ip_entry = tk.Entry(tunnel_client_window)
        dest_ip_entry.pack(padx=10, pady=5)

        tk.Label(tunnel_client_window, text="Message:").pack(padx=10, pady=5)
        message_entry = tk.Entry(tunnel_client_window)
        message_entry.pack(padx=10, pady=5)

        def send_packet():
            dest_ip = dest_ip_entry.get()
            message = message_entry.get()
            if dest_ip and message:
                self.chat_app.send_tunnel_packet(dest_ip, message)
            else:
                messagebox.showerror("Error", "Destination IP and message cannot be empty")

        send_button = tk.Button(tunnel_client_window, text="Send Packet", command=send_packet)
        send_button.pack(padx=10, pady=10)

        def on_close_tunnel_client():
            self.chat_app.close_tunnel()
            tunnel_client_window.destroy()

        tunnel_client_window.protocol("WM_DELETE_WINDOW", on_close_tunnel_client)

        self.chat_app.start_tunnel_client()

    def open_tunnel_gateway(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        tunnel_gateway_window = tk.Toplevel(self.master)
        tunnel_gateway_window.title("Tunnel Gateway")

        ip_address = self.chat_app.get_device_ip()
        if ip_address:
            message = f"Tunnel Gateway Setup\nDevice IP Address: {ip_address}"
        else:
            message = "Tunnel Gateway Setup\nDevice IP Address: Not available"

        tk.Label(tunnel_gateway_window, text=message).pack(padx=10, pady=10)
        self.chat_app.start_tunnel_gateway()

    def open_browser(self):
        if not self.chat_app:
            messagebox.showerror("Error", "Device not connected")
            return
        # Open a new window with a browser
        browser_window = tk.Toplevel(self.master)
        browser_window.title("Browser")
        
        # Create a webview window
        webview.create_window('Browser', 'https://www.google.com')

        # Start the webview window
        webview.start()
        
    def update_output(self, message, message_type="INFO"):
        self.output_text.configure(state='normal')
        self.output_text.insert(tk.END, message + "\n", message_type)
        self.output_text.configure(state='disabled')
        self.output_text.yview(tk.END)
    
        # Update message history for received messages
        if message_type == "RECEIVED":
            self.update_history(message)
        # Print to the terminal as well
        #print(message)
        
    def update_history(self, message):
        self.history_text.configure(state='normal')
        self.history_text.insert(tk.END, message + "\n")
        self.history_text.configure(state='disabled')
        self.history_text.yview(tk.END)

    def toggle_server(self):
        if self.chat_app.flask_server_running:
            self.chat_app.stop_flask_server()
            self.server_status_label.config(text="Server Status: Inactive", foreground="red")
            self.server_button.config(text="Run Server")
        else:
            self.chat_app.start_flask_server()
            self.server_status_label.config(text="Server Status: Running [port:5003]", foreground="green")
            self.server_button.config(text="Stop Server")
            
    def add_friend_right_click(self):
        selected_item = self.mesh_tree.item(self.mesh_tree.focus())
        self.FriendManager.add_friend(Friend().parse_selection_input(selected_item))
        self.update_friends_list()
        
    def right_click_popup(self, event):
        try: 
            self.right_click_menu.tk_popup(event.x_root, event.y_root) 
        finally: 
            self.right_click_menu.grab_release() 
    
    def run(self):
        self.master.mainloop()

if __name__ == "__main__":
    root = tk.Tk()
    app = MeshtasticTkinterApp(root)
    app.run()
