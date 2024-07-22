from flask import Flask, request, jsonify
import subprocess
import os
import sys
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)  # 최대 10개의 작업을 병렬로 실행

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
    box_id_output = subprocess.check_output(['isolate', '--cg', '--init']).decode().strip()
    box_id = box_id_output.split('/')[-1]
    box_path = f'/var/local/lib/isolate/{box_id}/box'

    cp_result = subprocess.run(['cp', file_name, box_path], capture_output=True, text=True)
    if cp_result.returncode != 0:
        return {'error': 'File copy failed', 'details': cp_result.stderr}

    if input_data:
        local_input_file = 'input.txt'
        with open(local_input_file, 'w') as f:
            f.write(input_data)

        cp_input_result = subprocess.run(['cp', local_input_file, box_path], capture_output=True, text=True)
        if cp_input_result.returncode != 0:
            return {'error': 'Input file copy failed', 'details': cp_input_result.stderr}

    # 프로그램 실행 및 메타 정보 수집
    if lang == 'python':
        result = run_isolate(box_id, ['/usr/bin/python3', f'/box/{file_name}'], input_data)
    elif lang == 'c':
        compile_command = [
            'isolate', '--cg', '--box-id', box_id, '--time=60', '--mem=64000', '--fsize=2048',
            '--wall-time=30', '--core=0', '--processes=10', '--run', '--', '/usr/bin/gcc',
            '-B', '/usr/bin/', f'/box/{file_name}', '-o', '/box/solution'
        ]
        compile_result = subprocess.run(compile_command, capture_output=True, text=True)
        if compile_result.returncode != 0:
            return {'result': 'Compile Error', 'details': compile_result.stderr}
        result = run_isolate(box_id, ['/box/solution'], input_data)

    subprocess.run(['isolate', '--cg', '--box-id', box_id, '--cleanup'])
    return result

def run_isolate(box_id, command, input_data):
    isolate_command = [
        'isolate', '--cg', '--box-id', box_id, 
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
