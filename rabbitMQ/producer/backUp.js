const express = require('express');
const bodyParser = require('body-parser');
const amqp = require('amqplib/callback_api');

const app = express();
app.use(bodyParser.json());

let currentQueue = 1; // 현재 큐 인덱스를 1로 초기화

amqp.connect('amqp://192.168.1.18', function(error0, connection) { // RabbitMQ 서버에 연결
    if (error0) {
        throw error0;
    }
    connection.createChannel(function(error1, channel) { // 채널을 생성합니다. 채널은 메시지를 보낼 때 사용
        if (error1) {
            throw error1;
        }
        const queues = Array.from({ length: 15 }, (_, i) => `task_queue_${i + 1}`);

        queues.forEach(queue => {
            // 각 큐를 선언. 큐가 없으면 생성하고, 있으면 기존 큐를 사용
            channel.assertQueue(queue, { // 각 큐를 생성, durable: true 옵션을 통해 RabbitMQ가 재시작해도 내용이 사라지지 않도록 보장
                durable: true
            });
        });

        app.post('/submit', (req, res) => { // 클라이언트로부터 POST 요청을 받으면, 요청 데이터를 메시지로 변환하여 큐에 전송
            const { code, lang, bojNumber, elapsed_time, limit_time, testCase} = req.body;

            if (!code || !lang || !bojNumber || !Array.isArray(testCase)) {
                return res.status(400).json({ error: 'Missing required fields' });
            }

            const message = JSON.stringify({ code, lang, bojNumber, elapsed_time, limit_time, testCase });
            const queue = `task_queue_${currentQueue}`; // 현재 큐를 선택

            channel.sendToQueue(queue, Buffer.from(message), { // 메시지를 큐에 보냄. persistent: true 옵션은 메시지가 디스크에 저장되도록 함.
                persistent: true
            });

            console.log(" [x] Sent '%s' to %s", message, queue);
            res.status(200).send('Message sent to queue');

            currentQueue = currentQueue < 15 ? currentQueue + 1 : 1; // 다음 큐로 이동, 15까지 갔다면 다시 1로 돌아감
        });

        // 결과를 수신할 엔드포인트 추가
        app.post('/results', (req, res) => {
            const { bojNumber, result } = req.body;
            if (!bojNumber || !result) {
                return res.status(400).json({ error: 'Missing required fields' });
            }

            console.log(`Received result for bojNumber ${bojNumber}:`, result);

            // 결과 처리 로직 추가
            // 예: 데이터베이스에 저장, 클라이언트에게 알림 등

            res.status(200).json({ message: 'Result received' });
        });


        app.listen(3000, () => {
            console.log('Producer server is running on port 3000');
        });
    });
});
