#!/usr/bin/env python
import pika
import sys

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

channel.queue_declare(queue='task_queue', durable=True)

message = ' '.join(sys.argv[1:]) or "Hello World!"  # 메세지는 arg로 받거나 없으면 Hello World를 보낸다.
channel.basic_publish(
    exchange='',
    routing_key='task_queue', # 여기서 routing queue는 보낼 queue를 이름을 지정한다.
    body=message,              # body에 메세지를 담아 보낸다.
    properties=pika.BasicProperties(
        delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
    ))
print(" [x] Sent %r" % message)
connection.close()