import os
import requests
import jwt
import datetime
import random
import string
import time
from flask import Flask, request, jsonify, send_file, after_this_request
from threading import Thread, Lock

app = Flask(__name__)

SECRET_KEY = '4uXKPqQjrhBPTxQ6dZlF'

TEMP_SESSIONS_DIR = 'temp_sessions'
COMPLETED_SESSIONS_DIR = 'completed_sessions'
if not os.path.exists(TEMP_SESSIONS_DIR):
    os.makedirs(TEMP_SESSIONS_DIR)
if not os.path.exists(COMPLETED_SESSIONS_DIR):
    os.makedirs(COMPLETED_SESSIONS_DIR)

task_status = {}
status_lock = Lock()

def create_jwt():
    expiration_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    token = jwt.encode({'exp': expiration_time}, SECRET_KEY, algorithm='HS256')
    return token

def generate_random_filename():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.json'

def get_proxy():
    response = requests.get('http://31.128.39.1:8081/get_proxy')
    response.raise_for_status()
    proxy_data = response.json()
    return proxy_data['proxy']

def send_request(proxy):
    url = 'http://31.128.39.1:8081/regNew'
    token = create_jwt()
    headers = {
        'Authorization': f'{token}',
        'Content-Type': 'application/json'
    }
    proxy_data = {"proxy": {"server": proxy}}
    
    try:
        response = requests.post(url, headers=headers, json=proxy_data)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, str(e)

def save_file(response_data):
    filename = generate_random_filename()
    temp_file_path = os.path.join(TEMP_SESSIONS_DIR, filename)
    
    with open(temp_file_path, 'w') as f:
        f.write(str(response_data))  # Save data as a string
    
    time.sleep(0.1)  # Pause to complete file operations
    
    completed_file_path = os.path.join(COMPLETED_SESSIONS_DIR, filename)
    os.rename(temp_file_path, completed_file_path)
    
    return filename

def delete_file_later(file_path):
    @after_this_request
    def remove_file(response):
        def try_delete():
            tries = 5
            for _ in range(tries):
                try:
                    time.sleep(1)  # Wait 1 second before each attempt
                    os.remove(file_path)
                    print(f"Successfully deleted {file_path}")
                    break
                except Exception as e:
                    print(f"Attempt to delete file {file_path} failed: {e}")

        Thread(target=try_delete).start()  # Perform deletion in a separate thread

        return response

def process_requests(task_id, num_requests):
    with status_lock:
        task_status[task_id] = 'running'
    successful_responses = []
    failed_requests = []

    while len(os.listdir(COMPLETED_SESSIONS_DIR)) < num_requests:
        proxy = get_proxy()
        response_data, error = send_request(proxy)

        if response_data:
            filename = save_file(response_data)
            successful_responses.append(filename)
        else:
            failed_requests.append(proxy)
            # Retry logic for failed requests
            retries = 3
            for _ in range(retries):
                response_data, error = send_request(proxy)
                if response_data:
                    filename = save_file(response_data)
                    successful_responses.append(filename)
                    break

    with status_lock:
        task_status[task_id] = 'completed'

@app.route('/send_requests', methods=['POST'])
def send_requests():
    try:
        num_requests = int(request.json.get('num_requests', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid number of requests'}), 400

    task_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    
    thread = Thread(target=process_requests, args=(task_id, num_requests))
    thread.start()

    return jsonify({'message': 'Task started', 'task_id': task_id}), 202

@app.route('/status/<task_id>', methods=['GET'])
def check_status(task_id):
    with status_lock:
        status = task_status.get(task_id, 'not_found')
    return jsonify({'task_id': task_id, 'status': status})

@app.route('/get_random_session', methods=['POST'])
def get_random_session():
    files = os.listdir(COMPLETED_SESSIONS_DIR)
    
    if not files:
        return jsonify({'error': 'No files available'}), 404

    random_file = random.choice(files)
    file_path = os.path.join(COMPLETED_SESSIONS_DIR, random_file)

    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        response = send_file(file_path, as_attachment=True)
        delete_file_later(file_path)
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8082)
