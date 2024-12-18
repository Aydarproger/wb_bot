import requests
import time
import random
import string

BASE_URL = 'http://127.0.0.1:8082'
NUM_REQUESTS = 10  # Number of requests to send per task

def generate_random_task_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def send_request():
    task_id = generate_random_task_id()
    response = requests.post(f'{BASE_URL}/send_requests', json={'num_requests': NUM_REQUESTS})
    
    if response.status_code == 202:
        print(f"Task started with ID: {task_id}")
        return task_id
    else:
        print(f"Failed to start task: {response.json()}")
        return None

def check_status(task_id):
    response = requests.get(f'{BASE_URL}/status/{task_id}')
    
    if response.status_code == 200:
        status = response.json().get('status')
        return status
    else:
        print(f"Failed to get status: {response.json()}")
        return None

def main():
    print("Waiting for 3 minutes before starting...")
    time.sleep(180)  # Wait for 3 minutes before starting the main task loop

    while True:
        task_id = send_request()
        if not task_id:
            print("Task could not be started. Exiting...")
            break

        while True:
            status = check_status(task_id)
            if status == 'completed':
                print("Task completed. Starting new task.")
                break
            elif status == 'not_found':
                print("Task ID not found. Exiting...")
                return
            else:
                print(f"Task status: {status}. Checking again in 5 minutes...")
                time.sleep(300)  # Wait for 5 minutes before checking the status again

if __name__ == '__main__':
    main()
