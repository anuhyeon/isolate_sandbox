const express = require('express');
const bodyParser = require('body-parser');
const amqp = require('amqplib/callback_api');
const app = express();

let currentQueue = 1;
const amqpURL = 'amqp://192.168.1.18';

app.use(bodyParser.json());

amqp.connect(amqpURL, (error0, connection) => {
    if (error0) {
        throw error0;
    }
    connection.createChannel((error1, channel) => {
        if (error1) {
            throw error1;
        }

        app.post('/submit', (req, res) => {
            const { code, lang, bojNumber, elapsed_time, limit_time, testCase } = req.body;

            if (!code || !lang || !bojNumber || !Array.isArray(testCase)) {
                return res.status(400).json({ error: '필드 누락' });
            }

            const correlationId = generateUuid();

            channel.assertQueue('', { exclusive: true }, (err, q) => {
                if (err) {
                    throw err;
                }

                const replyQueue = q.queue;

                const message = JSON.stringify({ code, lang, bojNumber, elapsed_time, limit_time, testCase });
                const queue = `task_queue_${currentQueue}`;

                channel.sendToQueue(queue, Buffer.from(message), {
                    persistent: true,
                    correlationId: correlationId,
                    replyTo: replyQueue
                });

                console.log(" [x] Sent '%s' to %s", message, queue);

                currentQueue = currentQueue < 15 ? currentQueue + 1 : 1;

                channel.consume(replyQueue, (msg) => {
                    //console.log(msg)
                    if (msg && msg.properties.correlationId === correlationId) {
                        res.status(200).json({ result: JSON.parse(msg.content.toString()) });
                        channel.deleteQueue(replyQueue);
                    }
                }, {
                    noAck: true
                });
            });
        });

        function generateUuid() {
            return Math.random().toString() + Math.random().toString() + Math.random().toString();
        }

        app.listen(3000, () => {
            console.log('서버가 3000 포트에서 실행 중입니다.');
        });
    });
});
