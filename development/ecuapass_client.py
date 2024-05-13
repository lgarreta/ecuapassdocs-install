import requests
import json
import time

# Function to submit a task to the server
def submit_task(task_id, duration):
    data = {'task_id': task_id, 'duration': duration}
    response = requests.post('http://localhost:5000/submit_task', json=data)
    return response.json()

# Function to retrieve results from the server
def get_results():
    response = requests.get('http://localhost:5000/get_results')
    return response.json()

def stop_server ():
    data = {'service': "doc", 'data': "d1" }
    response = requests.post('http://localhost:5000/start_processing', json=data)
    return response.json()


if __name__ == '__main__':
    # Submit multiple tasks
#    for task_id, duration in [('task1', 5), ('task2', 3), ('task3', 7)]:
#        result = submit_task(task_id, duration)
#        print(result['message'])
#
#    # Wait for tasks to complete (adjust as needed)
#    time.sleep(5)
#
#    # Retrieve and print results
#    results = get_results()
#    print("Results:")
#    for task_id, result in results.items():
#        print(f"Task {task_id}: {result}")
#
    # Stop server
    stop_server ()

