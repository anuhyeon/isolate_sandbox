from flask import Flask, request, jsonify
import subprocess
import os
import time
import psutil
import sys

# import resource

# def get_memory_usage():
#     usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
#     return f"Memory usage: {usage} KB"

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
    print('box_id_output :', box_id_output ,'\n')
    sys.stdout.flush()
    ########### 명령어 실행 후 디렉토리 상태 확인 -> 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ###########
    dir_output = subprocess.check_output(['ls', '-la', '/var/local/lib/isolate']).decode().strip()
    print(f"Directory content after isolate init: {dir_output}")
    sys.stdout.flush()
    #################################################################### 디버깅 ##################### 디버깅 ##################### 디버깅 ###########
    
    box_id = box_id_output.split('/')[-1]
    print('box_id :', box_id ,'\n')
    sys.stdout.flush()
    box_path = f'/var/local/lib/isolate/{box_id}/box'
    print('box_path :', box_path ,'\n')
    sys.stdout.flush()
    ########## 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ###########
    cp_result = subprocess.run(['cp', file_name, box_path], capture_output=True, text=True)
    if cp_result.returncode != 0:
        print(f"File copy error: {cp_result.stderr}")
        sys.stdout.flush()
        return jsonify({'error': 'File copy failed', 'details': cp_result.stderr}), 500

    # 파일 복사 후 디렉토리 상태 확인
    dir_0_output = subprocess.check_output(['ls', '-la', box_path]).decode().strip()
    print(f"Directory content inside '.../0/box': {dir_0_output}")
    sys.stdout.flush()
    ####################################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ###########
    # 프로그램 실행 및 메타 정보 수집
    result = None
    if lang == 'python':
        ################# 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ###########
        output = subprocess.check_output(['pwd']).decode().strip()
        print(f"pwd: {output}")
        sys.stdout.flush()
        
        output2 = subprocess.check_output(['ls', f'/var/local/lib/isolate/{box_id}/box/']).decode().strip()
        print(f"ls /var/local/lib/isolate/{box_id}/box/: {output2}")
        sys.stdout.flush()
        ################## 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ##################### 디버깅 ###########
        result = run_isolate(box_id, ['/usr/bin/python3',file_name]) #  f'/box/{file_name}' , f'/var/local/lib/isolate/{box_id}/box/{file_name}'
        print(' Python run_isolate result :', result, '\n')
        sys.stdout.flush()
    elif lang == 'c':
        # 샌드박스 내에서 ld를 찾을 수 있는지 확인하기 위해, 다음 명령어 사용
        # 샌드박스 내에서 환경 변수 및 설정을 확인합니다.
        check_env_command = ['isolate', '--box-id', box_id, '--run', '--', '/usr/bin/ld', '--version']
        env_output = subprocess.check_output(check_env_command).decode().strip()
        print('ld version inside sandbox:', env_output)
        sys.stdout.flush()

        # 샌드박스 내에서 GCC 컴파일러 실행
        compile_command = [
            'isolate', '--box-id', box_id, '--time=60', '--mem=64000', '--fsize=2048',
            '--wall-time=30', '--core=0', '--processes=10', '--run', '--', '/usr/bin/gcc',
            '-B', '/usr/bin/', f'/box/{file_name}', '-o', '/box/solution'
        ]  # -B 옵션 사용: gcc 명령어에 -B 옵션을 사용하여 ld의 경로를 명시적으로 지정      # compile_command = ['isolate', '--box-id', box_id, '--run', '--', '/usr/bin/gcc', f'/box/{file_name}', '-o', '/box/solution'] # '-o', '/box/solution']
        print('before compile \n','compile command :',compile_command)
        compile_result = subprocess.run(compile_command, capture_output=True, text=True)
        print('after compile \n')
        if compile_result.returncode != 0:
            return jsonify({'result': 'Compile Error', 'details': compile_result.stderr})
        result = run_isolate(box_id, ['solution'])
        print(' C run_isolate result :', result, '\n')
        sys.stdout.flush()

    subprocess.run(['isolate', '--box-id', box_id, '--cleanup'])

    return jsonify(result)

def run_isolate(box_id, command):
    start_time = time.time()
    #isolate_command = ['isolate', '--box-id', box_id, '--time=20', '--run', '--'] + command
    # 아래는 isolate 격리공간의 리소스를 조금 늘려주는 옵션
    isolate_command = [ 
        'isolate', '--box-id', box_id, 
        '--time=60', '--mem=64000', '--wall-time=30', '--run', '--meta=/box/meta.txt','--'
    ] + command  # '--fsize=2048'
    print('isolate_command :', isolate_command, '\n')
    sys.stdout.flush()
    process = subprocess.Popen(isolate_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    max_memory = 0
    ps_process = psutil.Process(process.pid)
    while process.poll() is None:
        try:
            max_memory = max(max_memory, ps_process.memory_info().rss)
        except psutil.NoSuchProcess:
            break
        time.sleep(0.1)
    
    stdout, stderr = process.communicate()
    end_time = time.time()
    execution_time = end_time - start_time

    if process.returncode != 0:
        if process.returncode == 137:  # Isolate returns 137 for time limit exceeded
            return {'result': 'Time Limit Exceeded', 'time': execution_time, 'memory': max_memory}
        return {'result': 'Runtime Error', 'details': stderr.decode(), 'time': execution_time, 'memory': max_memory}

    return {'result': 'Success', 'output': stdout.decode(), 'time': execution_time, 'memory': max_memory}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8181)
