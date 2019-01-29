let W3CWebSocket = require('websocket').w3cwebsocket;
let bilisocket = require("../utils/bilisocket");
let env = require("../config/proj_config").env;
let DEBUG = !(env === "server");

let loggers = require("../config/loggers");
let chat = loggers.chat;
let gold = loggers.gold;
let sliver = loggers.sliver;

chat.info("________Start Hansy recorder proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));
let USER_ID_TO_NAME = {
    20932326: "我自己",
    22218720: "寞寞",
    359496014: "阿音",
    38133678: "柳柳",
    28629254: "青词",
    13989100: "小克",
    24250809: "阿雨",
    10864099: "月度",
    15968297: "小炎",
};

let HANSY_ROOM_ID = 2516117;
let getCurrentTimest = () => {return parseInt((new Date()).valueOf().toString().slice(0, 10))};
let damakusender = require("../utils/danmakusender");
let sendDanmakuToHansyRoomId = (msg) => {
    damakusender.sendDanmaku(msg, HANSY_ROOM_ID, undefined, 0, undefined);
};
let HANSY_MSG_LIST = [
    "📢 小可爱们记得点上关注哟，点个关注不迷路ヽ(✿ﾟ▽ﾟ)ノ",
    "📢 喜欢泡泡的小伙伴，加粉丝群436496941来撩骚呀~",
    "📢 更多好听的原创歌和翻唱作品，网易云音乐搜索「管珩心」~",
    "📢 泡泡的海盗船正在招聘船长~欢迎加入舰队(✿≖ ◡ ≖)✧",
    "📢 赠送1个B坷垃，就可以领取珩心专属「电磁泡」粉丝勋章啦~",
    "📢 一定要来网易云关注「管珩心」哦，超多高质量单曲等你来听~",
];
let lastActiveUseTimeInHansysRoom = getCurrentTimest() - 120*HANSY_MSG_LIST.length;
let HANSY_MSG_LIST_INDEX = 0;
let intervalSendHansyDCallMsg = () => {
    if ((getCurrentTimest() - lastActiveUseTimeInHansysRoom) >= 120*HANSY_MSG_LIST.length){
        return;
    }
    HANSY_MSG_LIST_INDEX = (HANSY_MSG_LIST_INDEX + 1) % HANSY_MSG_LIST.length;
    sendDanmakuToHansyRoomId(HANSY_MSG_LIST[HANSY_MSG_LIST_INDEX])
};
if (!DEBUG){
    setInterval(intervalSendHansyDCallMsg, 120*1000);
}
let randomChoice = (l) => {
    l = l || [];
    return l[parseInt(Math.random()*l.length)];
};

let Gift = {
    __GIFT_LIST: {},
    __GIFT_THANK_TASK: 0,
    __LAST_THANK_USER: "$",
    sendThankDamaku: () => {
        let users = Object.keys(Gift.__GIFT_LIST);
        for (let i = 0; i < users.length; i++){
            let u = users[i];
            let gifts = Gift.__GIFT_LIST[u];
            delete Gift.__GIFT_LIST[u];

            if(Gift.__LAST_THANK_USER !== u){
                setTimeout(() => {
                    sendDanmakuToHansyRoomId("🤖 谢谢" + u + "赠送的" + gifts.join("、") + "~")
                }, 400*i);
                Gift.__LAST_THANK_USER = u;
            }
        }
        if(Gift.__GIFT_THANK_TASK !== 0){
            clearInterval(Gift.__GIFT_THANK_TASK);
            Gift.__GIFT_THANK_TASK = 0;
        }
    },
    addGift: (user, gift_name) => {
        if (Gift.__GIFT_LIST[user] === undefined){
            Gift.__GIFT_LIST[user] = [gift_name]
        }else if (Gift.__GIFT_LIST[user].indexOf(gift_name) < 0){
            Gift.__GIFT_LIST[user].push(gift_name)
        }

        if (Gift.__GIFT_THANK_TASK === 0) {
            Gift.__GIFT_THANK_TASK = setInterval(Gift.sendThankDamaku, 10000)
        }
    }
};

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
        );

        // if(uid in USER_ID_TO_NAME){USER_ID_TO_NAME[uname] = USER_ID_TO_NAME[uid]}
        // if(coin_type === "silver" && (getCurrentTimest() - lastActiveUseTimeInHansysRoom) < 120*HANSY_MSG_LIST.length){
        //     Gift.addGift(USER_ID_TO_NAME[uid] || uname, gift_name);
        // }
    }else if(msg.cmd === "COMBO_END"){
        // let uid = " combo ",
        //     uname = msg.data.uname,
        //     gift_name = msg.data.gift_name,
        //     price = msg.data.price,
        //     num = msg.data.combo_num;
        // gold.info("[%s][%s] -> %s * %s (%s)", uid, uname, gift_name, num, price);

        // uname = USER_ID_TO_NAME[uname] || uname;
        // setTimeout(() => {
        //     dmksender.sendDamaku("🤖 谢谢" + uname + "送的" + num + "个" + gift_name + "~", HANSY_ROOM_ID)
        // },  parseInt(Math.random()*3000));
    }else if(msg.cmd === "GUARD_BUY"){
        let uid = msg.data.uid,
            uname = msg.data.username,
            gift_name = msg.data.gift_name,
            num = msg.data.num,
            price = msg.data.price;
        gold.info("[%s][%s] -> %s * %s (%s)", uid, uname, gift_name, num, price);

        // if(uid in USER_ID_TO_NAME){USER_ID_TO_NAME[uname] = USER_ID_TO_NAME[uid]}
    }else if (msg.cmd === "DANMU_MSG"){
        let message = msg.info[1],
            uid = msg.info[2][0],
            username = msg.info[2][1],
            dl = msg.info[3][0],
            decoration = msg.info[3][1],
            ul = msg.info[4][0];
        chat.info("[ %d ] [UL %d] [%s %d] %s -> %s", uid, ul, decoration, dl, username, message);

        // if(uid in USER_ID_TO_NAME){USER_ID_TO_NAME[username] = USER_ID_TO_NAME[uid]}
        if(HANSY_MSG_LIST.indexOf(message) < 0){lastActiveUseTimeInHansysRoom = getCurrentTimest()}
        if (uid === 20932326 /*  */){return}

        if (message.indexOf("好听") > -1){
            if(Math.random() > 0.5){return;}
            sendDanmakuToHansyRoomId(randomChoice([
                "🤖 φ(≧ω≦*)♪好听好听！ 打call ᕕ( ᐛ )ᕗ",
                "🤖 好听！给跪了! ○|￣|_ (这么好听还不摁个关注？！",
                "🤖 好听! 我的大仙泡最美最萌最好听 ´･∀･)乂(･∀･｀",
            ]));
            return ;
        }

        if (uid === 65981801 && (message.indexOf("心") > -1 || message.indexOf("美") > -1 || message.indexOf("好") > -1)){
            sendDanmakuToHansyRoomId(randomChoice([
                "🤖 大连你是个大居蹄子！",
                "🤖 大连给我把你的舌头吞回去！",
                "🤖 大连啊大连，你在东北玩泥巴，我在大连木有家呀(￣△￣)~",
            ]))
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
