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
    file_name = f'solution.{lang}'  # 파일 확장자를 언어에 따라 설정
    if lang == 'python':
        compile_cmd = ['/usr/bin/python3', f'/box/{file_name}']
    elif lang == 'c':
        compile_cmd = ['/usr/bin/gcc', '-o', '/box/solution', f'/box/{file_name}']
    else:
        return {'error': 'Unsupported language'}

    # Isolate 초기화 및 파일 복사
    box_id = initialize_isolate()
    if not box_id:
        return {'error': 'Failed to initialize isolate'}

    box_path = f'/var/local/lib/isolate/{box_id}/box'

    if not copy_file_to_box(file_name, code, box_path):
        return {'error': 'Failed to copy code to isolate'}

    if input_data and not copy_input_to_box(input_data, box_path):
        return {'error': 'Failed to copy input to isolate'}

    # 프로그램 실행 및 메타 정보 수집
    if lang == 'python':
        result = run_isolate(box_id, compile_cmd, input_data)
    elif lang == 'c':
        compile_result = run_isolate(box_id, compile_cmd, input_data)
        if compile_result['result'] != 'Success':
            return compile_result
        result = run_isolate(box_id, ['/box/solution'], input_data)

    cleanup_isolate(box_id)
    return result

def initialize_isolate():
    try:
        output = subprocess.check_output(['isolate', '--cg', '--init']).decode().strip()
        return output.split('/')[-1]
    except subprocess.CalledProcessError as e:
        return None

def copy_file_to_box(file_name, content, box_path):
    try:
        with open(file_name, 'w') as f:
            f.write(content)
        subprocess.run(['cp', file_name, box_path], check=True)
        return True
    except (IOError, subprocess.CalledProcessError) as e:
        return False

def copy_input_to_box(input_data, box_path):
    try:
        input_file = 'input.txt'
        with open(input_file, 'w') as f:
            f.write(input_data)
        subprocess.run(['cp', input_file, box_path], check=True)
        return True
    except (IOError, subprocess.CalledProcessError) as e:
        return False

def run_isolate(box_id, command, input_data):
    isolate_command = [
        'isolate', '--cg', '--box-id', box_id, 
        '--time=60', '--mem=64000', '--wall-time=30', '--run', '--meta=/var/local/lib/isolate/{}/meta.txt'.format(box_id), '--'
    ] + command

    try:
        process = subprocess.Popen(isolate_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=input_data.encode() if input_data else None)

        with open(f'/var/local/lib/isolate/{box_id}/meta.txt', 'r') as meta_file:
            meta_content = meta_file.read()
            meta_info = parse_meta_file(meta_content)

        if process.returncode != 0:
            if process.returncode == 137:  # Isolate returns 137 for time limit exceeded
                return {'result': 'Time Limit Exceeded', **meta_info}
            return {'result': 'Runtime Error', 'details': stderr.decode(), **meta_info}

        return {'result': 'Success', 'output': stdout.decode(), **meta_info}
    except Exception as e:
        return {'error': 'Execution failed', 'details': str(e)}

def cleanup_isolate(box_id):
    subprocess.run(['isolate', '--cg', '--box-id', box_id, '--cleanup'])

def parse_meta_file(meta_content):
    meta_info = {}
    for line in meta_content.splitlines():
        if line:
            key, value = line.split(':', 1)
            meta_info[key.strip()] = value.strip()
    return meta_info

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8181)
