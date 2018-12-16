let WebSocketClient = require('websocket').client;
let fs = require("fs");
let request = require("request");
let PROC_NUMBER = parseInt(process.argv.splice(2)[0] || 0);
let PROC_SINGLE_THREAD = 900;

let log4js = require('log4js');

//var logger = log4js.getLogger();
let logerconf = {
  appenders: {
    acceptor_handler: {
      type: 'file',
      filename: './log/acceptor_handler_' + PROC_NUMBER + '.log',
      maxLogSize: 1024*1024*50,
      backups: 2,
    },
    prizeloger: {
      type: 'file',
      filename: './log/prizeloger.log',
      maxLogSize: 1024*1024*50,
      backups: 2,
    },
    console: { type: 'console' }
  },
  categories: {
    acceptor_handler: { appenders: ['acceptor_handler', 'console'], level: 'ALL' },
    prizeloger: { appenders: ['prizeloger', 'console'], level: 'ALL' },
    default: { appenders: ['console'], level: 'trace' }
  }
};

log4js.configure(logerconf);
let logging = log4js.getLogger('acceptor_handler');
let p_logging = log4js.getLogger('prizeloger');

/* ***************************** */

function generatePacket (action, payload) {
    payload = payload || '';
    let packetLength = Buffer.byteLength(payload) + 16;
    let buff = new Buffer.alloc(packetLength);

    buff.writeInt32BE(packetLength, 0);
    // write consts
    buff.writeInt16BE(16, 4);
    buff.writeInt16BE(1, 6);
    buff.writeInt32BE(1, 12);
    // write action
    buff.writeInt32BE(action, 8);
    // write payload
    buff.write(payload, 16);
    return buff
}

function sendJoinRoom(ws, rid){
    let uid = 1E15 + Math.floor(2E15 * Math.random());
    let packet = JSON.stringify({uid: uid, roomid: rid});
    let joinedRoomPayload = generatePacket(7, packet);
    ws.send(joinedRoomPayload);
}

function parseMessage(buff, fn, room_id){
    if(buff.length < 21) {return}
    while (buff.length > 16){
        let length = (buff[0] << 24) + (buff[1] << 16) + (buff[2] << 8) + buff[3];
        let current = buff.slice(0, length);
        buff = buff.slice(length);
        if (current.length > 16 && current[16] !== 0){
            try{
                let msg = JSON.parse("" + current.slice(16));
                fn(msg, room_id);
            }catch (e) {
                logging.error("e: " + current);
            }
        }
    }
}


let HEART_BEAT = generatePacket(2);
let MONITOR_URL = "ws://broadcastlv.chat.bilibili.com:2244/sub";
/* ***************************** */

let MESSAGE_COUNT = 0;

let ROOM_ID_POOL = new Set();
let CURRENT_CONNECTIONS = new Set();
let RESTARTING_CONNECTIONS = new Set();

function procMessage(msg, room_id){
    MESSAGE_COUNT += 1;

    if(msg.cmd === "SEND_GIFT"){
        if (msg.data.giftName !== "节奏风暴") return;
        let gtype = msg.data.giftName;
        let count = msg.data.num;
        logging.info("gift: ", gtype, "*", count, " - ", room_id);
        getStormId(room_id);
    }else if(msg.cmd === "GUARD_BUY"){
        let count = msg.data.num;
        let gid = msg.data.gift_id;
        let gname = msg.data.gift_name;
        logging.info("gift: ", gname, ", room_id: ", room_id, ", count: ", count);
    }
}


function create_monitor(room_id){
    if(!CURRENT_CONNECTIONS.has(room_id)) {return}

    let client = new WebSocketClient();
    function on_message(message){
        parseMessage(message.binaryData, procMessage, room_id);
    }
    function on_error(e){
        if (CURRENT_CONNECTIONS.has(room_id)){
            logging.error('Connect Error: ' + e.toString(), "room_id: ", room_id);
        }
        try{client.close();}catch (e) {}
        if(!RESTARTING_CONNECTIONS.has(room_id)) {
            RESTARTING_CONNECTIONS.add(room_id);
            setTimeout(function () {create_monitor(room_id)}, 1000);
        }
    }

    client.on('connectFailed', on_error);
    client.on('connect', function(connection) {
        connection.on('error', on_error);
        connection.on('close', on_error);
        connection.on('message', on_message);

        sendJoinRoom(connection, room_id);
        function sendHeartBeat() {
            if(CURRENT_CONNECTIONS.has(room_id) && connection.connected){
                connection.send(HEART_BEAT);
                setTimeout(sendHeartBeat, 10000);
            }
        }
        sendHeartBeat();
        if(RESTARTING_CONNECTIONS.has(room_id)){
            logging.info("Re connected: ", room_id);
        }
        RESTARTING_CONNECTIONS.delete(room_id);
    });
    client.connect(MONITOR_URL);
}


function updateMonitor(){
    let roomList = fs.readFileSync('./rooms.txt', "utf-8").split("_");
    logging.info("Rooms length: ", roomList.length);
    if (roomList.length < PROC_SINGLE_THREAD*PROC_NUMBER){
        return ;
    }
    let start = PROC_SINGLE_THREAD*PROC_NUMBER;
    let end = Math.min(roomList.length, PROC_SINGLE_THREAD*(PROC_NUMBER + 1));
    ROOM_ID_POOL.clear();
    for (let i = start; i < end; i++){
        ROOM_ID_POOL.add(parseInt(roomList[i]));
    }

    logging.info("ROOM_ID_POOL: size -> ", ROOM_ID_POOL.size);
    CURRENT_CONNECTIONS.forEach(function (room_id) {
        if (!ROOM_ID_POOL.has(room_id)){
            logging.info("Delete: ", room_id);
            CURRENT_CONNECTIONS.delete(room_id);
        }
    });
    ROOM_ID_POOL.forEach(function(room_id){
        if(!CURRENT_CONNECTIONS.has(room_id)){
            CURRENT_CONNECTIONS.add(room_id);
            logging.info("Create: ", room_id);
            create_monitor(room_id);
        }
    });
}

let cookie = fs.readFileSync('./cookie.txt', "utf-8");
let cookie_kv = cookie.split(";");
let csrf_token = "";
for (let i = 0; i < cookie_kv.length; i++){
    let kvstr = cookie_kv[i];
    if (kvstr.indexOf("bili_jct") > -1){
        csrf_token = kvstr.split("=")[1].trim();
        break;
    }
}
let headers = {
    "User-Agent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
    "Cookie": cookie
};
function getStormGift(room_id, gift_id, req_times){
    req_times = req_times || 0;
    let parseResponse = function (err, res, body) {
        if (err) {
            logging.error("Err: ", err);
            getStormGift(room_id, gift_id, req_times + 1);
        } else {
            let r = JSON.parse(body);
            if (r.code !== 0){
                if(req_times < 100){
                    if (req_times > 30 && (req_times%7) === 0){
                        setTimeout(function(){getStormGift(room_id, gift_id, req_times + 1);}, 130)
                    }else{
                        getStormGift(room_id, gift_id, req_times + 1);
                    }
                }else{
                    p_logging.error("Failed! ", room_id);
                }
            }else{
                p_logging.info("Succeed! ", room_id, r.data.mobile_content, ", req_times: ", req_times);
            }
        }
    };
    let reqParam = {
        url: "https://api.live.bilibili.com/lottery/v1/Storm/join",
        headers: headers,
        timeout: 5000,
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
    };
    request.post(reqParam, parseResponse);
}
function getStormId(room_id){
    let parseStormId = function (err, res, body) {
        if (err) {
            logging.error("Error: ", err);
        } else {
            let r = JSON.parse(body);
            if (r.code === 0 && r.data.hasJoin === 0) {
                logging.info("getStormGift: ", room_id, ", ", r.data.id)
                getStormGift(room_id, r.data.id);
            }
        }
    };
    let reqParam = {
        url: "https://api.live.bilibili.com/lottery/v1/Storm/check?roomid=" + room_id,
        method: "get",
        headers: headers,
        timeout: 5000,
    };
    request(reqParam, parseStormId);
}



setInterval(function (){
    logging.info(MESSAGE_COUNT + " messages received.");
    if (MESSAGE_COUNT > 999999999999){MESSAGE_COUNT = 0;}
}, 1000*60);

setInterval(updateMonitor, 1000*60*5);
console.log("Started.");
updateMonitor();
