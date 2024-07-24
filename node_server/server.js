const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cors());

// 메인 서버에서 채점 서버로 요청을 보내는 엔드포인트
app.post('/submit', async (req, res) => {
    const { code, lang, input } = req.body;
    console.log(code, lang, input)

    try {
        // 채점 서버로 코드 제출
        const response = await axios.post('http://172.16.151.85:8181/submit', { 
            code: code,
            lang: lang,
            input: input
        });

        // 채점 결과를 클라이언트에 반환
        console.log(response.data," from flask server in nodeserver")
        res.json(response.data);
    } catch (error) {
        console.error('Error:', error.response ? error.response.data : error.message);
        res.status(500).json({ error: '채점 서버와 통신 중 오류 발생' });
    }
});

const port = 1234;
app.listen(port, () => {
    console.log(`Main server is running on port ${port}`);
});
