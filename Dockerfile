# 베이스 이미지 설정
FROM python:3.10-slim

# 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    pkg-config \
    gcc \
    make \ 
    git \
    libcap-dev \
    libsystemd-dev \
    python3 \
    python3-pip 

# Isolate 설치
RUN git clone https://github.com/ioi/isolate.git && \
    cd isolate && \
    make isolate &&\
    make install

# Flask 및 필요한 Python 패키지 설치
RUN pip3 install flask psutil

# # isolate 실행에 필요한 권한 설정
# RUN echo 'ALL ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# # 작업 디렉토리 설정
# WORKDIR /root

# # Flask 애플리케이션 복사
# COPY . .

# 애플리케이션 디렉토리 설정
WORKDIR /app

# 애플리케이션 코드 복사
COPY . /app

# Flask 애플리케이션 실행
CMD ["python3", "app.py"]


# 이미지 빌드, 컨테이너 실행 명령어
# docker build -t judge-server .
# docker run --name judge-container --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw -d -p 8181:8181 judge-server
#

