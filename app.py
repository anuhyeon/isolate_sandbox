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
    bojNumber = data.get('bojNumber')
    elapsed_time = data.get('elapsed_time', 0)
    limit_time = data.get('limit_time', 0)
    test_case = data.get('testCase', [])

    if not code or not lang or not bojNumber or test_case is None:
        return jsonify({'error': 'Missing required fields'}), 400

    print(f"Received request for bojNumber: {bojNumber}")  # 요청 수신 로그
    sys.stdout.flush()

    # 비동기 실행을 위해 executor에 작업 제출
    future = executor.submit(execute_code, code, lang, bojNumber, elapsed_time, limit_time, test_case)
    result = future.result()  # 결과를 기다림

    print(f"Execution result for bojNumber {bojNumber}: {result}")  # 실행 결과 로그
    sys.stdout.flush()

    return jsonify(result)

def execute_code(code, lang, bojNumber, elapsed_time, limit_time, test_case):
    if lang == 'python':
        file_name = 'solution.py'
    elif lang == 'c':
        file_name = 'solution.c'
    else:
        return {'error': 'Unsupported language'}

    with open(file_name, 'w') as f:
        f.write(code)

    print(f"Code written to {file_name} for bojNumber {bojNumber}")  # 코드 작성 로그
    sys.stdout.flush()

    # Isolate 초기화 및 파일 복사
    box_id = initialize_isolate_box()
    if box_id is None:
        return {'error': 'No available boxes'}

    print(f"Initialized isolate box {box_id} for bojNumber {bojNumber}")  # 박스 초기화 로그
    sys.stdout.flush()

    box_path = f'/var/local/lib/isolate/{box_id}/box'

    cp_result = subprocess.run(['cp', file_name, box_path], capture_output=True, text=True)
    if cp_result.returncode != 0:
        cleanup_isolate_box(box_id)
        return {'error': 'File copy failed', 'details': cp_result.stderr}

    print(f"Copied file to isolate box {box_id} for bojNumber {bojNumber}")  # 파일 복사 로그
    sys.stdout.flush()
    
    if not test_case:  # 테스트 케이스가 빈 경우 기본 실행
        print(f"No test cases provided, running default execution for bojNumber {bojNumber}")
        sys.stdout.flush()
        if lang == 'python':
            result = run_isolate(box_id, ['/usr/bin/python3', f'/box/{file_name}'], '')
        elif lang == 'c':
            compile_command = [
                'isolate', '--cg', '--box-id', str(box_id), '--time=10', '--mem=64000', '--fsize=2048',
                '--wall-time=10', '--core=0', '--processes=10', '--run', '--', '/usr/bin/gcc',
                '-B', '/usr/bin/', f'/box/{file_name}', '-o', '/box/solution'
            ]
            compile_result = subprocess.run(compile_command, capture_output=True, text=True)
            if compile_result.returncode != 0:
                cleanup_isolate_box(box_id)
                return {'result': 'Compile Error', 'details': compile_result.stderr}
            result = run_isolate(box_id, ['/box/solution'], '')

        cleanup_isolate_box(box_id)
        return {'bojNumber': bojNumber, 'results': result}

    # test_case 실행 및 결과 수집
    test_case_results = run_tests(box_id, lang, file_name, test_case, bojNumber)

    cleanup_isolate_box(box_id)
    return {'bojNumber': bojNumber, 'results': test_case_results}

def run_tests(box_id, lang, file_name, test_cases, bojNumber):
    results = []

    for case in test_cases:
        input_data = case.get('input_case', '')
        expected_output = str(case.get('output_case')).strip()

        print(f"Running test case with input: {input_data} for bojNumber {bojNumber}")  # 테스트 케이스 실행 로그
        sys.stdout.flush()

        # 프로그램 실행 및 메타 정보 수집
        if lang == 'python':
            result = run_isolate(box_id, ['/usr/bin/python3', f'/box/{file_name}'], input_data)
        elif lang == 'c':
            compile_command = [
                'isolate', '--cg', '--box-id', str(box_id), '--time=10', '--mem=64000', '--fsize=2048',
                '--wall-time=10', '--core=0', '--processes=10', '--run', '--', '/usr/bin/gcc',
                '-B', '/usr/bin/', f'/box/{file_name}', '-o', '/box/solution'
            ]
            compile_result = subprocess.run(compile_command, capture_output=True, text=True)
            if compile_result.returncode != 0:
                cleanup_isolate_box(box_id)
                return {'result': 'Compile Error', 'details': compile_result.stderr}
            result = run_isolate(box_id, ['/box/solution'], input_data)

        actual_output = result.get('output', '').strip()
        result['expected_output'] = expected_output
        result['correct'] = (expected_output == actual_output)
        results.append(result)

        print(f"Test case result: {result} for bojNumber {bojNumber}")  # 테스트 케이스 결과 로그
        sys.stdout.flush()

    return results

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
        print(f"Cleaned up isolate box {box_id}")  # 박스 정리 로그
        sys.stdout.flush()

def run_isolate(box_id, command, input_data):
    isolate_command = [
        'isolate', '--cg', '--box-id', str(box_id), 
        '--time=5', '--mem=64000', '--wall-time=5', '--run', '--meta=/var/local/lib/isolate/{}/meta.txt'.format(box_id), '--'
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
