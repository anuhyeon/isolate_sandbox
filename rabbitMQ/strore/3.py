import pika
import requests
import json
import concurrent.futures
import sys

AMQP_URL = 'amqp://myuser:mypassword@13.209.214.53:5672'

def callback(ch, method, properties, body):
    data = json.loads(body)
    try:
        # 요청 데이터 구조에 맞게 post 요청 전송
        response = requests.post('http://13.209.214.53:8181/submit', json={
            "code": data.get("code"),
            "lang": data.get("lang"),
            "bojNumber": data.get("bojNumber"),
            "elapsed_time": data.get("elapsed_time", 0),
            "limit_time": data.get("limit_time", 0),
            "testCase": data.get("testCase", [])
        })
        response.raise_for_status()  # HTTP 에러가 발생하면 예외를 발생시킴
        try:
            result = response.json()
            print(result)
            sys.stdout.flush()


            # 클라이언트에게 결과 전송
            ch.basic_publish(
                exchange='',
                routing_key=properties.reply_to,
                properties=pika.BasicProperties(correlation_id=properties.correlation_id),
                body=json.dumps(result)
            )
            print("Result sent to client")

        except json.JSONDecodeError:
            print("Response is not in JSON format")
            sys.stdout.flush()
     
    except requests.RequestException as e:
        print(f"HTTP Request failed: {e}")
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)

def consume_messages(queue_name):
    connection_params = pika.URLParameters(AMQP_URL)
    connection = pika.BlockingConnection(connection_params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)

    channel.basic_qos(prefetch_count=1)  # 한 번에 1개의 메시지를 가져옴
    channel.basic_consume(queue=queue_name, on_message_callback=callback)

    print(f'Waiting for messages in {queue_name}. To exit press CTRL+C')
    sys.stdout.flush()

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("Exiting...")
        channel.stop_consuming()
    finally:
        connection.close()

def main():
    queue_names = [f'task_queue_{i}' for i in range(1, 16)]  # 15개의 큐 이름 생성
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(consume_messages, queue_name) for queue_name in queue_names]  # 각 큐에 대해 소비자 생성
        try:
            for future in concurrent.futures.as_completed(futures):
                future.result()  # 스레드의 결과를 기다림
        except KeyboardInterrupt:
            print("Exiting...")

if __name__ == "__main__":
    main()
