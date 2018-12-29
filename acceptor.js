let W3CWebSocket = require('websocket').w3cwebsocket;
let logger = require("./utils/logger");
let path = require('path');
let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let loggerFilePath = DEBUG ? "./log" : "/home/wwwroot/log",
    loggerConfigList = [{
        loggerName: "acceptor",
        loggerFile: path.join(loggerFilePath, "acceptor.log"),
    }];


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
            loggerConfigList.push({
                loggerName: csrf_token,
                loggerFile: path.join(loggerFilePath, "apz_" + csrf_token.slice(csrf_token.length/2) + ".log"),
            });
            break;
        }
    }
}

let loggers = logger.batchCreateLogger(loggerConfigList);
let logging = loggers["acceptor"];
logging.info("Start proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));

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

let Acceptor = require("./utils/acceptprize").Acceptor;
let ac = new Acceptor(COOKIE_DICT_LIST, loggers, logging);

let Tac = require("./utils/tvacceptor").Acceptor;
Tac.init(COOKIE_DICT_LIST, loggers, logging);

let onMessageReceived = (msg) => {
    if (msg.length < 5 ){return}
    let sendGuardNotice = msg[0] === "_",
        giftType = msg[1],
        room_id = parseInt(msg.slice(2));

    if(giftType === "S"){
        logging.info("Gift: %s, room_id: %s", giftType, room_id);
    }else if(giftType === "G"){
        logging.info("Gift: %s, room_id: %s", giftType, room_id);
        ac.acceptGuard(room_id);
        if(sendGuardNotice){
            sendNoticeDanmakuMsg(room_id, "G");
        }
    }else if(giftType === "T"){
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
        client.onmessage = (e) => {onMessageReceived(e.data)};
    };
    ConnectToNoticeServer();
})();
