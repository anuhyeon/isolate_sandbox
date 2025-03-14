from flask import Flask, request, jsonify
import subprocess
import os
import sys
from concurrent.futures import ThreadPoolExecutor
import threading

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)  # 최대 10개의 작업을 병렬로 실행
lock = threading.Lock()  # 박스 ID 할당을 위한 락

# 사용 가능한 박스 ID를 관리하는 집합
available_boxes = set(range(16))

@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'Invalid JSON'}), 400

    code = data.get('code')
    lang = data.get('lang')
    input_data = data.get('input', '')  # 입력 값을 받아옵니다. 기본값은 빈 문자열

    if not code or not lang:
        return jsonify({'error': 'Missing code or language'}), 400

    # 비동기 실행을 위해 executor에 작업 제출
    future = executor.submit(execute_code, code, lang, input_data)
    result = future.result()  # 결과를 기다림

    return jsonify(result)

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
    #print('##########',box_id,'#############')
    #sys.stdout.flush()
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
    app.run(host='0.0.0.0', port=8181)
