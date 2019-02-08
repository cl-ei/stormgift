let W3CWebSocket = require('websocket').w3cwebsocket;
let log4js = require("log4js");
let bilisocket = require("./bilisocket");
let path = require('path');

let loggerFilePath = "/home/wwwroot/log/lyy";
let config = {
    appenders: {
        gold: {
            type: 'file',
            filename: path.join(loggerFilePath, "gold.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        sliver: {
            type: 'file',
            filename: path.join(loggerFilePath, "sliver.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        gift: {
            type: 'file',
            filename: path.join(loggerFilePath, "gift.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        mix: {
            type: 'file',
            filename: path.join(loggerFilePath, "mix.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        chat: {
            type: 'file',
            filename: path.join(loggerFilePath, "chat.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        console: {type: 'console'}
    },
    categories: {
        chat: { appenders: ["chat", "mix"], level: 'ALL'},
        gold: { appenders: ["gold", "mix", "gift"], level: 'ALL'},
        sliver: { appenders: ["sliver", "mix", "gift"], level: 'ALL'},
        default: { appenders: ['console'], level: 'ALL'}
    }
};
log4js.configure(config);
let chat = log4js.getLogger("chat"),
    gold = log4js.getLogger("gold"),
    sliver = log4js.getLogger("sliver");

chat.info("________Start Lyy recorder proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));

let MONITOR_ROOM_ID = 92450;

let procMessage = (msg, room_id) => {
    if(msg.cmd === "SEND_GIFT"){
        let uid = msg.data.uid,
            uname = msg.data.uname,
            coin_type = msg.data.coin_type,
            total_coin = msg.data.total_coin,
            gift_name = msg.data.giftName,
            num = msg.data.num;
        (coin_type === "gold" ? gold : sliver).info(
            "[%d][%s] -> %s - %s * %s (%s)",
            uid, uname, coin_type, gift_name, num, total_coin
        )
    }else if(msg.cmd === "GUARD_BUY"){
        let uid = msg.data.uid,
            uname = msg.data.username,
            gift_name = msg.data.gift_name,
            num = msg.data.num,
            price = msg.data.price;
        gold.info("[%s][%s] -> %s * %s (%s)", uid, uname, gift_name, num, price)
    }else if (msg.cmd === "DANMU_MSG"){
        let message = msg.info[1],
            uid = msg.info[2][0],
            username = msg.info[2][1],
            dl = msg.info[3][0],
            decoration = msg.info[3][1],
            ul = msg.info[4][0];
        chat.info("[ %d ] [UL %d] [%s %d] %s -> %s", uid, ul, decoration, dl, username, message);
    }
};

(function (){
    let client = new W3CWebSocket(bilisocket.MONITOR_URL);
    client.onerror = () => {
        chat.error("Client unexpected error!");
        throw "Client unexpected error!";
    };
    client.onopen = () => {
        bilisocket.sendJoinRoom(client, MONITOR_ROOM_ID);
        function sendHeartBeat() {
            if (client.readyState === client.OPEN){
                client.send(bilisocket.HEART_BEAT_PACKAGE);
                setTimeout(sendHeartBeat, 10000);
            }
        }
        sendHeartBeat();
    };
    client.onclose = () => {
        chat.error("Client unexpected closed!");
        throw "Client unexpected closed!";
    };
    client.onmessage = function(e) {
        bilisocket.parseMessage(e.data, MONITOR_ROOM_ID, procMessage);
    };
})();
