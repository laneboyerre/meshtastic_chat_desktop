from flask import Flask, request, jsonify, render_template
import os
import base64
import threading
import time
from colorama import Fore, init
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app)

heartbeat_interval = 30  # Heartbeat interval in seconds

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send', methods=['POST'])
def send_message():
    data = request.json
    destination_id = data.get('destination_id')
    text_message = data.get('text_message')
    group_message = data.get('group_message')
    data_message = data.get('data_message')
    file_message = data.get('file_message')
    ip_data_url = data.get('ip_data_url')
    channel_index = int(data.get('channel_index', 0))  # Ensure channel_index is an integer
    subscribe = data.get('subscribe')
    unsubscribe = data.get('unsubscribe')
    verbose = data.get('verbose', False)

    chat_app = app.config.get('chat_app')

    if not chat_app:
        return jsonify({"error": "Chat app not configured"}), 500

    if subscribe:
        subscriber_id = data.get('subscriber_id')
        chat_app.subscribers[subscriber_id] = {
            "verbose": verbose,
            "last_heartbeat": time.time(),
            "sid": request.sid
        }
        print(Fore.GREEN + f"Subscribed {subscriber_id} with SID: {request.sid}")
        return jsonify({"message": f"Subscribed {subscriber_id}"}), 200

    if unsubscribe:
        subscriber_id = data.get('subscriber_id')
        chat_app.subscribers.pop(subscriber_id, None)
        print(Fore.RED + f"Unsubscribed {subscriber_id}")
        return jsonify({"message": f"Unsubscribed {subscriber_id}"}), 200

    if text_message:
        chat_app.send_text_message(text_message, channel_index, destination_id)
        return jsonify({"message": "Text message sent"}), 200

    if group_message:
        chat_app.send_group_message(group_message, channel_index)
        return jsonify({"message": "Group message sent"}), 200

    if data_message:
        chat_app.send_data(data_message.encode('utf-8'), channel_index)
        return jsonify({"message": "Data message sent"}), 200

    if file_message:
        file_path = save_file(file_message, request.remote_addr)
        if file_path:
            try:
                with open(file_path, 'rb') as file:
                    file_data = file.read()
                    file_name = os.path.basename(file_path)
                    chat_app.send_data_in_chunks(file_data, file_name, channel_index=channel_index)
                    return jsonify({"message": f"File {file_name} sent"}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    if ip_data_url:
        chat_app.send_ip_data_in_chunks(ip_data_url, channel_index=channel_index)
        return jsonify({"message": f"IP data from {ip_data_url} sent"}), 200

    return jsonify({"error": "Invalid request"}), 400

@app.route('/send_ip_data', methods=['POST'])
def send_ip_data():
    data = request.json
    ip_data_url = data.get('ip_data_url')
    destination_id = data.get('destination_id')
    channel_index = int(data.get('channel_index', 0))  # Ensure channel_index is an integer

    chat_app = app.config.get('chat_app')

    if not chat_app:
        return jsonify({"error": "Chat app not configured"}), 500

    chat_app.send_ip_data_in_chunks(ip_data_url, destination_id=destination_id, channel_index=channel_index)
    return jsonify({"message": "IP data request sent"}), 200

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    subscriber_id = data.get('subscriber_id')

    chat_app = app.config.get('chat_app')
    if not chat_app:
        return jsonify({"error": "Chat app not configured"}), 500

    if subscriber_id in chat_app.subscribers:
        chat_app.subscribers[subscriber_id]['last_heartbeat'] = time.time()
        print(Fore.BLUE + f"Heartbeat received from {subscriber_id}")
        return jsonify({"message": "Heartbeat received"}), 200
    else:
        print(Fore.RED + f"Heartbeat received from unknown subscriber {subscriber_id}")
        return jsonify({"error": "Subscription not found"}), 404

def save_file(file_message, client_addr):
    # Save the file temporarily on the server
    try:
        file_name = file_message.get('name')
        file_content = file_message.get('content')
        if not file_name or not file_content:
            raise ValueError("File name or content is missing")

        file_path = os.path.join('uploads', client_addr, file_name)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as file:
            file.write(base64.b64decode(file_content))

        return file_path
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

def heartbeat_monitor(chat_app):
    while True:
        current_time = time.time()
        for subscriber_id, info in list(chat_app.subscribers.items()):
            if current_time - info['last_heartbeat'] > heartbeat_interval * 2:
                print(Fore.RED + f"Subscriber {subscriber_id} timed out")
                chat_app.subscribers.pop(subscriber_id)
        time.sleep(heartbeat_interval)

def start_heartbeat_monitor(chat_app):
    threading.Thread(target=heartbeat_monitor, args=(chat_app,), daemon=True).start()

@socketio.on('subscribe')
def handle_subscribe(data):
    chat_app = app.config.get('chat_app')
    if not chat_app:
        emit('error', {'message': "Chat app not configured"})
        return

    subscriber_id = data.get('subscriber_id')
    verbose = data.get('verbose', False)

    chat_app.subscribers[subscriber_id] = {
        "verbose": verbose,
        "last_heartbeat": time.time(),
        "sid": request.sid
    }
    print(Fore.GREEN + f"Subscribed {subscriber_id} with SID: {request.sid}")
    emit('success', {'message': f"Subscribed {subscriber_id}"})

@socketio.on('unsubscribe')
def handle_unsubscribe(data):
    chat_app = app.config.get('chat_app')
    if not chat_app:
        emit('error', {'message': "Chat app not configured"})
        return

    subscriber_id = data.get('subscriber_id')

    if subscriber_id in chat_app.subscribers:
        chat_app.subscribers.pop(subscriber_id, None)
        print(Fore.RED + f"Unsubscribed {subscriber_id}")
        emit('success', {'message': f"Unsubscribed {subscriber_id}"})

@socketio.on('send_message')
def handle_send_message(data):
    chat_app = app.config.get('chat_app')
    if not chat_app:
        emit('error', {'message': "Chat app not configured"})
        return

    text_message = data.get('text_message')
    data_message = data.get('data_message')
    file_message = data.get('file_message')
    ip_data_url = data.get('ip_data_url')
    channel_index = int(data.get('channel_index', 0))  # Ensure channel_index is an integer
    destination_id = data.get('destination_id')

    if text_message:
        chat_app.send_text_message(text_message, channel_index, destination_id)
        emit('success', {'message': "Text message sent"})

    if data_message:
        chat_app.send_data(data_message.encode('utf-8'), channel_index)
        emit('success', {'message': "Data message sent"})

    if file_message:
        file_path = save_file(file_message, request.remote_addr)
        if file_path:
            try:
                with open(file_path, 'rb') as file:
                    file_data = file.read()
                    file_name = os.path.basename(file_path)
                    chat_app.send_data_in_chunks(file_data, file_name, channel_index=channel_index)
                    emit('success', {'message': f"File {file_name} sent"})
            except Exception as e:
                emit('error', {'message': str(e)})
        else:
            emit('error', {'message': "Failed to save file"})
    
    if ip_data_url:
        chat_app.send_ip_data_in_chunks(ip_data_url, destination_id=destination_id, channel_index=channel_index)
        emit('success', {'message': f"IP data from {ip_data_url} sent"})

@socketio.on('request_ip_data')
def handle_request_ip_data(data):
    chat_app = app.config.get('chat_app')
    if not chat_app:
        emit('error', {'message': "Chat app not configured"})
        return

    ip_data_url = data.get('ip_data_url')
    channel_index = int(data.get('channel_index', 0))  # Ensure channel_index is an integer
    destination_id = data.get('destination_id')

    chat_app.request_ip_data(ip_data_url, destination_id, channel_index=channel_index)
    emit('success', {'message': f"IP data request for {ip_data_url} sent"})
    
@socketio.on('heartbeat')
def handle_heartbeat(data):
    chat_app = app.config.get('chat_app')
    if not chat_app:
        emit('error', {'message': "Chat app not configured"})
        return

    subscriber_id = data.get('subscriber_id')

    if subscriber_id in chat_app.subscribers:
        chat_app.subscribers[subscriber_id]['last_heartbeat'] = time.time()
        print(Fore.BLUE + f"Heartbeat received from {subscriber_id}")
        emit('success', {'message': f"Heartbeat received from {subscriber_id}"})
    else:
        print(Fore.RED + f"Heartbeat received from unknown subscriber {subscriber_id}")
        emit('error', {'message': f"Subscription not found for {subscriber_id}"})
