let W3CWebSocket = require('websocket').w3cwebsocket;
let request = require("request");
let logger = require("./utils/logger");
let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let loggerFilePath = DEBUG ? "./log" : "/home/wwwroot/log";
let logging = logger.creatLogger("stormacceptor", loggerFilePath);

let cookie_filename = './data/cookie.js';
let RAW_COOKIES_LIST = require(cookie_filename).RAW_COOKIE_LIST;
let cookie = RAW_COOKIES_LIST[0];
let cookie_kv = cookie.split(";");
let csrf_token = "";
for (let i = 0; i < cookie_kv.length; i++){
    let kvstr = cookie_kv[i];
    if (kvstr.indexOf("bili_jct") > -1){
        csrf_token = kvstr.split("=")[1].trim();
         break;
    }
}
logging.info("Start stormacceptor proc -> env: %s, csrf_token: %s",  (DEBUG ? "DEBUG" : "SERVER"), csrf_token);

let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
let headers = {"User-Agent": UA, "Cookie": cookie};

function acceptStormGift(room_id){
    let stormJoin = (room_id, gift_id, req_times) => {
        req_times = req_times || 0;
        request.post({
            url: "https://api.live.bilibili.com/lottery/v1/Storm/join",
            headers: headers,
            timeout: 10000,
            form: {
                id: gift_id,
                color: 8322816,
                captcha_token: "",
                captcha_phrase: "",
                roomid: room_id,
                csrf_token: csrf_token,
                csrf: csrf_token,
                visit_id: "",
            }
        },
        (err, res, body) => {
            if (err) {
                logging.error("Err: ", err);
                return;
            }
            let r = {};
            try{r = JSON.parse(body)}catch (e) {return}
            if (r.code === 0) {
                let data = r.data || {};
                logging.info(
                    "Get storm gift success! room_id: %s, msg: %s, req_times: %s",
                    room_id, data.mobile_content, req_times
                );
                return;
            }
            if(req_times >= 50) {
                logging.error("Failed! room_id: %s, req_times: %s, r.code: %s", room_id, req_times, r.code);
                return;
            }
            setTimeout(
                function(){stormJoin(room_id, gift_id, req_times + 1)},
                Math.random()*300
            )
        })
    };
    request({
        url: "https://api.live.bilibili.com/lottery/v1/Storm/check?roomid=" + room_id,
        method: "get",
        headers: headers,
        timeout: 10000,
    }, (err, res, body) => {
        if (err) {
            logging.error("Error: ", err);
            return;
        }
        let r = {};
        try{r = JSON.parse(body)}catch (e) {return}
        let data = r.data || {};
        if (r.code === 0 && data.hasJoin === 0) {
            logging.info("getStormGift room_id: %s, gift_id: %s", room_id, data.id);
            stormJoin(room_id, data.id);
        }
    });
}

let onMessageReceived = (msg) => {
    if (msg.length < 5 ){return}
    let sendNotice = msg[0] === "_",
        giftType = msg[1],
        room_id = parseInt(msg.slice(2));

    if(giftType === "S"){
        logging.info("Gift: %s, room_id: %s", giftType, room_id);
        acceptStormGift(room_id);
    }
};


(() => {
    let ConnectToNoticeServer = () => {
        let client = new W3CWebSocket("ws://127.0.0.1:11112");
        client.onerror = () => {
            logging.error("Connection to notice server error! Try reconnect...");
            client.onclose = undefined;
            setTimeout(ConnectToNoticeServer, 1000);
        };
        client.onopen = () => {
            function sendHeartBeat() {
                if (client.readyState === client.OPEN){
                    client.send("HEARTBEAT");
                    setTimeout(sendHeartBeat, 10000);
                }
            }
            sendHeartBeat();
        };
        client.onclose = () => {
            logging.error("ConnectToNoticeServer closed! Try reconnect...");
            setTimeout(ConnectToNoticeServer, 500);
        };
        client.onmessage = (e) => {onMessageReceived(e.data)};
    };
    ConnectToNoticeServer();
})();
