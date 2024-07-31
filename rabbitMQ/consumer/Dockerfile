# 베이스 이미지 설정
FROM --platform=linux/amd64 python:3.9-slim

# Flask 및 필요한 Python 패키지 설치
RUN pip3 install pika requests

# 애플리케이션 디렉토리 설정
WORKDIR /mq

# 애플리케이션 코드 복사
COPY . /mq

# Flask 애플리케이션 실행
CMD ["python3", "app.py"]



