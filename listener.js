let WebSocketClient = require('websocket').client;
let fs = require("fs");
let path = require('path');
let log4js = require('log4js');
let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let PROC_NUMBER = parseInt(sysArgs[1]) || 0;


function creatLogger(loggerName, path_){
  let config = {
    appenders: {console: { type: 'console' }},
    categories: {default: { appenders: ['console'], level: 'trace' }}
  };
  config.appenders[loggerName] = {
        type: 'file',
        filename: path.join(path_, loggerName+ ".log"),
        maxLogSize: 1024*1024*50,
        backups: 2,
  };
  config.categories[loggerName] = {appenders: [loggerName, 'console'], level: 'ALL' };
  log4js.configure(config);
  return log4js.getLogger(loggerName);
}

let logging = creatLogger('listener', DEBUG ? "./log/" : "/home/wwwroot/log/");
logging.info("Start proc -> proc num: " + PROC_NUMBER);


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
    }
    // else if(msg.cmd === "GUARD_BUY"){
    //     let count = msg.data.num;
    //     let gid = msg.data.gift_id;
    //     let gname = msg.data.gift_name;
    //     logging.info("gift: ", gname, ", room_id: ", room_id, ", count: ", count);
    // }
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
    setTimeout(function(){client.connect(MONITOR_URL)}, parseInt(Math.random()*10000));
}


function updateMonitor(){
    let roomList = fs.readFileSync('./rooms.txt', "utf-8").split("_");
    logging.info("Rooms length: ", roomList.length);

    ROOM_ID_POOL.clear();
    for (let room_id in roomList){
        let postfixnum = parseInt(room_id[room_id.length-1]);
        room_id = parseInt(room_id);
        if(postfixnum === PROC_NUMBER || postfixnum === (5 + PROC_NUMBER)){
            ROOM_ID_POOL.add(parseInt(room_id));
        }
    }

    CURRENT_CONNECTIONS.forEach(function (room_id) {
        if (!ROOM_ID_POOL.has(room_id)){
            logging.info("Delete: ", room_id);
            CURRENT_CONNECTIONS.delete(room_id);
        }
    });
    ROOM_ID_POOL.forEach(function(room_id){
        if(!CURRENT_CONNECTIONS.has(room_id)){
            CURRENT_CONNECTIONS.add(room_id);
            create_monitor(room_id);
        }
    });
}


setInterval(function (){
    logging.info(MESSAGE_COUNT + " messages received.");
    if (MESSAGE_COUNT > 999999999999){MESSAGE_COUNT = 0;}
}, 1000*60);

setInterval(updateMonitor, 1000*60*5);
updateMonitor();
