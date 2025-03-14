import pika
import requests
import json
import concurrent.futures

def callback(ch, method, properties, body):
    data = json.loads(body)
    try:
        response = requests.post('http://192.168.1.18:8181/submit', json=data)
        response.raise_for_status()  # HTTP 에러가 발생하면 예외를 발생시킴
        try:
            print(response.json())
        except json.JSONDecodeError:
            print("Response is not in JSON format")
    except requests.RequestException as e:
        print(f"HTTP Request failed: {e}")
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)

def consume_messages(queue_name):
    connection_params = pika.ConnectionParameters(host='192.168.1.18')
    connection = pika.BlockingConnection(connection_params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)

    channel.basic_qos(prefetch_count=1)  # 한 번에 15개의 메시지를 가져옴
    channel.basic_consume(queue=queue_name, on_message_callback=callback)

    print(f'Waiting for messages in {queue_name}. To exit press CTRL+C')
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

