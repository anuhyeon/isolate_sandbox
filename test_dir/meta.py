from flask import Flask, request, jsonify
import subprocess
import os
import sys

app = Flask(__name__)

@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'Invalid JSON'}), 400

    code = data.get('code')
    lang = data.get('lang')
    print('-----------------------')
    print(code)
    print(lang)
    print('-----------------------')
    sys.stdout.flush()

    if not code or not lang:
        print("#######  error 1 ######")
        sys.stdout.flush()
        return jsonify({'error': 'Missing code or language'}), 400

    if lang == 'python':
        file_name = 'solution.py'
    elif lang == 'c':
        file_name = 'solution.c'
    else:
        print("#######  error 2 ######")
        sys.stdout.flush()
        return jsonify({'error': 'Unsupported language'}), 400

    with open(file_name, 'w') as f:
        f.write(code)

    # Isolate 초기화 및 파일 복사
    box_id_output = subprocess.check_output(['isolate', '--init']).decode().strip()
    box_id = box_id_output.split('/')[-1]
    box_path = f'/var/local/lib/isolate/{box_id}/box'

    cp_result = subprocess.run(['cp', file_name, box_path], capture_output=True, text=True)
    if cp_result.returncode != 0:
        print(f"File copy error: {cp_result.stderr}")
        sys.stdout.flush()
        return jsonify({'error': 'File copy failed', 'details': cp_result.stderr}), 500

    # 프로그램 실행 및 메타 정보 수집
    result = None
    if lang == 'python':
        result = run_isolate(box_id, ['/usr/bin/python3', f'/box/{file_name}'])
    elif lang == 'c':
        # 샌드박스 내에서 GCC 컴파일러 실행
        compile_command = [
            'isolate', '--box-id', box_id, '--time=60', '--mem=64000', '--fsize=2048',
            '--wall-time=30', '--core=0', '--processes=10', '--run', '--', '/usr/bin/gcc',
            '-B', '/usr/bin/', f'/box/{file_name}', '-o', '/box/solution'
        ]
        compile_result = subprocess.run(compile_command, capture_output=True, text=True)
        if compile_result.returncode != 0:
            return jsonify({'result': 'Compile Error', 'details': compile_result.stderr})
        result = run_isolate(box_id, ['/box/solution'])

    subprocess.run(['isolate', '--box-id', box_id, '--cleanup'])

    return jsonify(result)

def run_isolate(box_id, command):
    # isolate 명령어 실행
    isolate_command = [
        'isolate', '--box-id', box_id, 
        '--time=60', '--mem=64000', '--wall-time=30', '--run', '--meta=/var/local/lib/isolate/{}/meta.txt'.format(box_id), '--'
    ] + command
    process = subprocess.Popen(isolate_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stdout, stderr = process.communicate()

    # 메타파일 읽기
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
