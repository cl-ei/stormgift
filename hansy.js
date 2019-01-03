let W3CWebSocket = require('websocket').w3cwebsocket;
let log4js = require("log4js");
let bilisocket = require("./utils/bilisocket");
let path = require('path');

let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let loggerFilePath = DEBUG ? "./log" : "/home/wwwroot/log/hansy";
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
        chat: { appenders: ['console', "chat", "mix"], level: 'ALL'},
        gold: { appenders: ['console', "gold", "mix", "gift"], level: 'ALL'},
        sliver: { appenders: ['console', "sliver", "mix", "gift"], level: 'ALL'},
        default: { appenders: ['console'], level: 'ALL'}
    }
};
log4js.configure(config);
let chat = log4js.getLogger("chat"),
    gold = log4js.getLogger("gold"),
    sliver = log4js.getLogger("sliver");

chat.info("________Start Hansy recorder proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));

let HANSY_ROOM_ID = 2516117;
let getCurrentTimest = () => {return parseInt((new Date()).valueOf().toString().slice(0, 10))};
let damakusender = require("./utils/danmakusender");
let dmksender = new damakusender.Sender(0, chat);
let HANSY_MSG_LIST = [
    "📢 小可爱们记得点上关注哟，点个关注不迷路ヽ(✿ﾟ▽ﾟ)ノ",
    "📢 喜欢泡泡的小伙伴，加粉丝群436496941来撩骚呀~",
    "📢 更多好听的原创歌和翻唱作品，网易云音乐搜索「管珩心」~",
    "📢 泡泡的海盗船正在招聘船长~欢迎加入舰队(✿≖ ◡ ≖)✧",
    "📢 获取「电磁泡」勋章：赠送1个B坷垃，或充电50电池~",
    "📢 一定要来网易云关注「管珩心」哦，超多高质量单曲等你来听~",
];
let lastActiveUseTimeInHansysRoom = getCurrentTimest() - 120*HANSY_MSG_LIST.length;
let HANSY_MSG_LIST_INDEX = 0;
let intervalSendHansyDCallMsg = () => {
    if ((getCurrentTimest() - lastActiveUseTimeInHansysRoom) >= 120*HANSY_MSG_LIST.length){
        return;
    }
    HANSY_MSG_LIST_INDEX = (HANSY_MSG_LIST_INDEX + 1) % HANSY_MSG_LIST.length;
    dmksender.sendDamaku(HANSY_MSG_LIST[HANSY_MSG_LIST_INDEX], HANSY_ROOM_ID)
};
if (!DEBUG){
    setInterval(intervalSendHansyDCallMsg, 120*1000);
}

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
    }else if(msg.cmd === "COMBO_END"){
        let uid = " combo ",
            uname = msg.data.uname,
            gift_name = msg.data.gift_name,
            price = msg.data.price,
            num = msg.data.combo_num;
        gold.info("[%s][%s] -> %s * %s (%s)", uid, uname, gift_name, num, price)
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

        if (uid === 20932326 /*  */){return}

        lastActiveUseTimeInHansysRoom = getCurrentTimest();
        if (message.indexOf("好听") > -1){
            if(Math.random() > 0.5){return;}
            dmksender.sendDamaku(
                [
                    "🤖 φ(≧ω≦*)♪好听好听！ 打call ᕕ( ᐛ )ᕗ",
                    "🤖 好听！给跪了! ○|￣|_ (这么好听还不摁个关注？！",
                    "🤖 好听! 我的大仙泡最美最萌最好听 ´･∀･)乂(･∀･｀",
                ][Math.floor((Math.random()*3)+1)],
                HANSY_ROOM_ID
            )
        }
    }
};

(function (){
    let client = new W3CWebSocket(bilisocket.MONITOR_URL);
    client.onerror = () => {
        chat.error("Client unexpected error!");
        throw "Client unexpected error!";
    };
    client.onopen = () => {
        bilisocket.sendJoinRoom(client, HANSY_ROOM_ID);
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
        bilisocket.parseMessage(e.data, HANSY_ROOM_ID, procMessage);
    };
})();
