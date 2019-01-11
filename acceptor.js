let W3CWebSocket = require('websocket').w3cwebsocket;

let logging = require("./config/loggers").acceptor;
logging.info("Start acceptor proc.");


let cookie_filename = './data/cookie.js';
let RAW_COOKIES_LIST = require(cookie_filename).RAW_COOKIE_LIST,
    COOKIE_DICT_LIST = [];
for (let i = 0; i < RAW_COOKIES_LIST.length; i++){
    let cookie = RAW_COOKIES_LIST[i];
    let cookie_kv = cookie.split(";");
    let csrf_token = "";
    for (let i = 0; i < cookie_kv.length; i++){
        let kvstr = cookie_kv[i];
        if (kvstr.indexOf("bili_jct") > -1){
            csrf_token = kvstr.split("=")[1].trim();
            COOKIE_DICT_LIST.push({
               cookie: cookie,
               csrf_token: csrf_token,
            });
            break;
        }
    }
}

let damakusender = require("./utils/danmakusender");
let dmksender = new damakusender.Sender(1, logging);
let DDSLIVE_ROOM_NUMBER = 13369254;
let sendNoticeDanmakuMsg = (room_id, gift_type) => {
    // let message = "#@" + sender + "在" + room_id + "直播间登船~";
    let message = gift_type + Buffer.from("" + room_id).toString('base64');
    setTimeout(
        function(){dmksender.sendDamaku(message, DDSLIVE_ROOM_NUMBER)},
        parseInt(Math.random()*1000)
    );
};

let Gac = require("./utils/guard_acceptor_directly").Acceptor;
Gac.init(COOKIE_DICT_LIST);

let Tac = require("./utils/tvacceptor").Acceptor;
Tac.init(COOKIE_DICT_LIST);

let onMessageReceived = (msg) => {
    let source = msg[0],
        giftType = msg[1],
        msgBody = msg.slice(2);

    if(source === "N" && giftType === "G"){
        logging.info("Gift: %s, msgBody: %s", giftType, msgBody);
        Gac.accept(msgBody);

    }else if(giftType === "T"){
        let room_id = parseInt(msgBody);
        logging.info("Gift: %s, room_id: %s", giftType, room_id);
        Tac.accept(room_id);
        sendNoticeDanmakuMsg(room_id, "T");
    }
};


(() => {
    let ConnectToNoticeServer = () => {
        let client = new W3CWebSocket("ws://127.0.0.1:11112");
        client.onerror = () => {
            logging.error("Connection to notice server error! Try reconnect...");
            client.onclose = undefined;
            setTimeout(ConnectToNoticeServer, 500);
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
        client.onmessage = (e) => {
            let mList = e.data.match(/(_T|_G|XG|_S|NG)\d{3,}\$?\d{3,}/g) || [];
            for(let i = 0; i < mList.length; i++){onMessageReceived(mList[i])}
        };
    };
    ConnectToNoticeServer();
})();
