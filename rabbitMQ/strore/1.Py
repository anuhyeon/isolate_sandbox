from flask import Flask, request, jsonify
import subprocess
import os
import sys
import pika
import threading
import json

app = Flask(__name__)
lock = threading.Lock()  # 박스 ID 할당을 위한 락

# 사용 가능한 박스 ID를 관리하는 집합
available_boxes = set(range(16))

def initialize_rabbitmq():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='192.168.1.18')) # 동기적 연결을 설정, 연결에 필요한 매개변수를 설정 -> host는 파라미터로 RabbitMQ서버의 IP주소를 지정
    channel = connection.channel() # 해당 코드는 RabbitMQ채널을 여는 코드로 채널은 RabbitMQ연결 내에서 통신을 위한 가벼운 컨텍스트라고 보면됨
    channel.queue_declare(queue='task_queue', durable=True) # task_queue라는 이름의 큐를 선언(메시지를 저장하는 큐임), durable=True는 RabbitMQ서버가 재시작 되더라도 큐가 사라지지 않도록 함.

    def callback(ch, method, properties, body): # callback함수는 큐에서 메시지를 받을 때 호출됨.
        try:
            data = json.loads(body) # 클라이언트->메인서버 로부터 받은 메시지의 본문임.(코드정보)
            result = process_task(data) # isolate환경에서 돌리는 내가 정의한 채점 함수
            print(f" [x] Received {data}, Result: {result}")
            ch.basic_ack(delivery_tag=method.delivery_tag) # 메시지가 설공적으로 처리되었음을 RabbitMQ에 알리고 이를 통해 해당 메시지가 큐에서 제거됨.
        except json.JSONDecodeError as e: # 메시지가 JSON 형식이 아니거나 디코딩 중 오류가 발생하면 예외처리
            print(f"Failed to decode JSON: {e}, body: {body}") 
            ch.basic_ack(delivery_tag=method.delivery_tag) # 오류가 발생하면 basic_ack를 호출하여 해당 메시지를 큐에서 제거함.

    channel.basic_qos(prefetch_count=10) # RabbitMQ에게 한번에 하나의 메시지만 소비자에게 보내도록 지시 -> 메시지 처리량 조절하고 채점 서버가 과부하되지 않도록함.
    channel.basic_consume(queue='task_queue', on_message_callback=callback) # task_queue에서 메시지를 소비하겠다고 선언 -> 메시지가 수신되면(consumer가 task_queue로 부터 메시지를 수신하면) callback 함수 호출
    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming() # 메시지 소비를 시작 -> 해당 함수는 무한 루프를 실행하여 큐에서 메시지를 계속해서 가져오고 콜백함수를 호출함.

def process_task(data):
    code = data.get('code')
    lang = data.get('lang')
    input_data = data.get('input', '')  # 입력 값을 받아옵니다. 기본값은 빈 문자열

    if not code or not lang:
        return {'error': 'Missing code or language'}

    return execute_code(code, lang, input_data)

def execute_code(code, lang, input_data):
    if lang == 'python':
        file_name = 'solution.py'
    elif lang == 'c':
        file_name = 'solution.c'
    else:
        return {'error': 'Unsupported language'}

    with open(file_name, 'w') as f:
        f.write(code)

    # Isolate 초기화 및 파일 복사
    box_id = initialize_isolate_box()
    if box_id is None:
        return {'error': 'No available boxes'}

    print(f"Current box_id: {box_id}")  # 현재 실행중인 box_id 출력
    sys.stdout.flush()

    box_path = f'/var/local/lib/isolate/{box_id}/box'

    cp_result = subprocess.run(['cp', file_name, box_path], capture_output=True, text=True)
    if cp_result.returncode != 0:
        cleanup_isolate_box(box_id)
        return {'error': 'File copy failed', 'details': cp_result.stderr}

    if input_data:
        local_input_file = 'input.txt'
        with open(local_input_file, 'w') as f:
            f.write(input_data)

        cp_input_result = subprocess.run(['cp', local_input_file, box_path], capture_output=True, text=True)
        if cp_input_result.returncode != 0:
            cleanup_isolate_box(box_id)
            return {'error': 'Input file copy failed', 'details': cp_input_result.stderr}

    # 프로그램 실행 및 메타 정보 수집
    if lang == 'python':
        result = run_isolate(box_id, ['/usr/bin/python3', f'/box/{file_name}'], input_data)
    elif lang == 'c':
        compile_command = [
            'isolate', '--cg', '--box-id', str(box_id), '--time=60', '--mem=64000', '--fsize=2048',
            '--wall-time=30', '--core=0', '--processes=10', '--run', '--', '/usr/bin/gcc',
            '-B', '/usr/bin/', f'/box/{file_name}', '-o', '/box/solution'
        ]
        compile_result = subprocess.run(compile_command, capture_output=True, text=True)
        if compile_result.returncode != 0:
            cleanup_isolate_box(box_id)
            return {'result': 'Compile Error', 'details': compile_result.stderr}
        result = run_isolate(box_id, ['/box/solution'], input_data)

    cleanup_isolate_box(box_id)
    return result

def initialize_isolate_box():
    with lock:
        for _ in range(5):  # 최대 5번 재시도
            try:
                if available_boxes:
                    box_id = available_boxes.pop()
                    subprocess.check_output(['isolate', '--cg', '--box-id', str(box_id), '--init']).decode().strip()
                    return box_id
            except subprocess.CalledProcessError as e:
                print(f"Box initialization failed: {e}")
                sys.stdout.flush()
                if box_id in available_boxes:
                    available_boxes.add(box_id)  # 실패 시 박스 ID 다시 추가
                continue
        return None  # 사용 가능한 박스가 없으면 None 반환

def cleanup_isolate_box(box_id):
    with lock:
        subprocess.run(['isolate', '--cg', '--box-id', str(box_id), '--cleanup'])
        available_boxes.add(box_id)

def run_isolate(box_id, command, input_data):
    isolate_command = [
        'isolate', '--cg', '--box-id', str(box_id), 
        '--time=60', '--mem=64000', '--wall-time=30', '--run', '--meta=/var/local/lib/isolate/{}/meta.txt'.format(box_id), '--'
    ] + command

    process = subprocess.Popen(isolate_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate(input=input_data.encode() if input_data else None)

    meta_file_path = '/var/local/lib/isolate/{}/meta.txt'.format(box_id)
    with open(meta_file_path, 'r') as meta_file:
        meta_content = meta_file.read()
        meta_info = parse_meta_file(meta_content)

    if process.returncode != 0:
        if process.returncode == 137:  # Isolate returns 137 for time limit exceeded
            return {'result': 'Time Limit Exceeded', **meta_info}
        return {'result': 'Runtime Error', 'details': stderr.decode(), **meta_info}

    return {'result': 'Success', 'output': stdout.decode(), **meta_info}

def parse_meta_file(meta_content):
    meta_info = {}
    for line in meta_content.splitlines():
        if line:
            key, value = line.split(':', 1)
            meta_info[key.strip()] = value.strip()
    return meta_info

if __name__ == '__main__':
    threading.Thread(target=initialize_rabbitmq).start()
    app.run(host='0.0.0.0', port=8181)
