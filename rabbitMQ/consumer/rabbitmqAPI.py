import requests
from requests.auth import HTTPBasicAuth

# RabbitMQ 서버 정보
rabbitmq_url = 'http://192.168.1.18:15672/api/queues'
username = 'guest'
password = 'guest'

# 큐 상태 확인
response = requests.get(rabbitmq_url, auth=HTTPBasicAuth(username, password))
queues = response.json()

# 각 큐의 메시지 수 출력
for queue in queues:
    print(f"Queue: {queue['name']}, Messages: {queue['messages']}")
