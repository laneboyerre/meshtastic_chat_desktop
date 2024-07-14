const socket = io();

const subscribeBtn = document.getElementById('subscribeBtn');
const unsubscribeBtn = document.getElementById('unsubscribeBtn');
const subscriberIdInput = document.getElementById('subscriberId');
const messageForm = document.getElementById('messageForm');
const messageInput = document.getElementById('messageInput');
const destinationIdInput = document.getElementById('destinationIdInput');
const channelIndexInput = document.getElementById('channelIndexInput');
const dataForm = document.getElementById('dataForm');
const dataInput = document.getElementById('dataInput');
const destinationIdDataInput = document.getElementById('destinationIdDataInput');
const channelIndexDataInput = document.getElementById('channelIndexDataInput');
const fileForm = document.getElementById('fileForm');
const fileInput = document.getElementById('fileInput');
const destinationIdFileInput = document.getElementById('destinationIdFileInput');
const channelIndexFileInput = document.getElementById('channelIndexFileInput');
const sendIpDataForm = document.getElementById('sendIpDataForm');
const sendIpDataUrlInput = document.getElementById('sendIpDataUrlInput');
const destinationIdSendIpDataInput = document.getElementById('destinationIdSendIpDataInput');
const channelIndexSendIpDataInput = document.getElementById('channelIndexSendIpDataInput');
const requestIpDataForm = document.getElementById('requestIpDataForm');
const requestIpDataUrlInput = document.getElementById('requestIpDataUrlInput');
const destinationIdRequestIpDataInput = document.getElementById('destinationIdRequestIpDataInput');
const channelIndexRequestIpDataInput = document.getElementById('channelIndexRequestIpDataInput');
const messagesContainer = document.getElementById('messages');
const ipDataContainer = document.getElementById('ipData');
const verboseCheckbox = document.getElementById('verbose');

let heartbeatInterval;
let ipDataContent = '';

subscribeBtn.addEventListener('click', () => {
    const subscriber_id = subscriberIdInput.value || 'defaultSubscriber';
    const verbose = verboseCheckbox.checked;
    socket.emit('subscribe', { subscriber_id, verbose });

    // Start sending heartbeats
    heartbeatInterval = setInterval(() => {
        socket.emit('heartbeat', { subscriber_id });
        console.log(`Heartbeat sent from ${subscriber_id}`);
    }, 10000); // Send heartbeat every 10 seconds
});

unsubscribeBtn.addEventListener('click', () => {
    const subscriber_id = subscriberIdInput.value || 'defaultSubscriber';
    socket.emit('unsubscribe', { subscriber_id });

    // Stop sending heartbeats
    clearInterval(heartbeatInterval);
});

messageForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text_message = messageInput.value;
    const destination_id = destinationIdInput.value;
    const channel_index = parseInt(channelIndexInput.value);
    socket.emit('send_message', { text_message, destination_id, channel_index });
    messageInput.value = '';
    addMessageToHistory(`You: ${text_message}`);
});

dataForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const data_message = dataInput.value;
    const destination_id = destinationIdDataInput.value;
    const channel_index = parseInt(channelIndexDataInput.value);
    socket.emit('send_message', { data_message, destination_id, channel_index });
    dataInput.value = '';
    addMessageToHistory(`You: ${data_message}`);
});

fileForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    const destination_id = destinationIdFileInput.value;
    const channel_index = parseInt(channelIndexFileInput.value);
    const reader = new FileReader();
    
    reader.onload = function(event) {
        const fileContent = event.target.result.split(',')[1]; // Get the base64 encoded content
        const fileMessage = {
            name: file.name,
            content: fileContent
        };
        socket.emit('send_message', { file_message: fileMessage, destination_id, channel_index });
    };
    
    reader.readAsDataURL(file);
    addMessageToHistory(`You sent a file: ${file.name}`);
});

sendIpDataForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const ip_data_url = sendIpDataUrlInput.value;
    const destination_id = destinationIdSendIpDataInput.value;
    const channel_index = parseInt(channelIndexSendIpDataInput.value);
    socket.emit('send_message', { ip_data_url, destination_id, channel_index });
    addMessageToHistory(`You sent IP data from: ${ip_data_url}`);
});

requestIpDataForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const ip_data_url = requestIpDataUrlInput.value;
    const destination_id = destinationIdRequestIpDataInput.value;
    const channel_index = parseInt(channelIndexRequestIpDataInput.value);
	
	// Clear the existing IP data content
    ipDataContent = '';
    ipDataContainer.innerHTML = '';
	
    socket.emit('request_ip_data', { ip_data_url, destination_id, channel_index });
    addMessageToHistory(`You requested IP data from: ${ip_data_url}`);
});

socket.on('message', (data) => {
    addMessageToHistory(`${data.sender_id}: ${data.message}`);
});

socket.on('ip_data', (data) => {
    appendIpData(data.content);
});

socket.on('success', (data) => {
    console.log(data.message);
});

socket.on('error', (data) => {
    console.error(data.message);
});

function addMessageToHistory(message) {
    const messageElement = document.createElement('div');
    messageElement.textContent = message;
    messagesContainer.appendChild(messageElement);
    messagesContainer.scrollTop = messagesContainer.scrollHeight; // Scroll to the bottom
}

function appendIpData(ipData) {
    if (ipData && typeof ipData === 'string') {
        // Log the received IP data for debugging
        console.log('Received IP data:', ipData);

        // Remove the numerical identifier at the beginning
        const cleanedData = ipData.replace(/^\d+:/, '');

        // Log the cleaned data for debugging
        console.log('Cleaned IP data:', cleanedData);

        ipDataContent += cleanedData;
        ipDataContainer.innerHTML = ipDataContent;
        ipDataContainer.scrollTop = ipDataContainer.scrollHeight; // Scroll to the bottom
    } else {
        console.error('Invalid IP data received:', ipData);
    }
}

// Collapsible sections for messages and IP data
const toggleMessagesBtn = document.getElementById('toggleMessagesBtn');
const toggleIpDataBtn = document.getElementById('toggleIpDataBtn');

toggleMessagesBtn.addEventListener('click', () => {
    const content = document.getElementById('messagesContainer');
    content.style.display = content.style.display === 'none' ? 'block' : 'none';
});

toggleIpDataBtn.addEventListener('click', () => {
    const content = document.getElementById('ipDataContainer');
    content.style.display = content.style.display === 'none' ? 'block' : 'none';
});
