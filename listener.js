let W3CWebSocket = require('websocket').w3cwebsocket;
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

let logging = creatLogger('listener_' + PROC_NUMBER, DEBUG ? "./log/" : "/home/wwwroot/log/");
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

function sendJoinRoom(client, rid){
    let uid = 1E15 + Math.floor(2E15 * Math.random());
    let packet = JSON.stringify({uid: uid, roomid: rid});
    let joinedRoomPayload = generatePacket(7, packet);
    client.send(joinedRoomPayload);
}

function parseMessage(arrayBuffer, room_id){
    if(arrayBuffer.byteLength < 21) {return}

    let buff = Buffer.from(arrayBuffer);
    let view = new Uint8Array(arrayBuffer);
    for (let i = 0; i < buff.length; ++i) {buff[i] = view[i]}
    while (buff.length > 16){
        let length = (buff[0] << 24) + (buff[1] << 16) + (buff[2] << 8) + buff[3];
        let current = buff.slice(0, length);
        buff = buff.slice(length);
        if (current.length > 16 && current[16] !== 0){
            try{
                let msg = JSON.parse("" + current.slice(16));
                procMessage(msg, room_id);
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
let CURRENT_CONNECTIONS = {};

function procMessage(msg, room_id){
    MESSAGE_COUNT += 1;

    if(msg.cmd === "SEND_GIFT"){
        if (msg.data.giftName !== "节奏风暴") return;
        let count = msg.data.num;
        logging.info("Storm gift -> count: " + count + ", room_id: " + room_id);
    }
    else if(msg.cmd === "GUARD_BUY"){
        let count = msg.data.num;
        let gid = msg.data.gift_id;
        let gname = msg.data.gift_name;
        logging.info("Guard gift -> " + gname + ", count: " + count + ", room_id: " + room_id + ", gid: " + gid);
    }
}


function createClients(room_id){
    let existedClient = CURRENT_CONNECTIONS[room_id],
        reconnectFlag = false;
    if(existedClient){
        if(existedClient.readyState === 1) {
            logging.error("CODE ERROR! do not create duplicated client.");
            return
        }else{
            reconnectFlag = true;
        }
    }

    let client = new W3CWebSocket(MONITOR_URL);
    client.onerror = function(err) {
        if(ROOM_ID_POOL.has(room_id)){
            let existedClient = CURRENT_CONNECTIONS[room_id];
            if(existedClient){
                if (existedClient === client){
                    logging.error('UNEXPECTED Connection Error happened, room id: ' + room_id);
                    setTimeout(function(){createClients(room_id)}, Math.random()*10000)
                }else{
                    logging.error('Connection Removed (EXPECTED, but caused by duplicated!), room id: ' + room_id);
                }
            }
        }else{
            logging.error('Connection Removed (EXPECTED, but caused by error), room id: ' + room_id +', err: ' + err.toString());
        }
    };
    client.onclose = function() {
        if(ROOM_ID_POOL.has(room_id)){
            let existedClient = CURRENT_CONNECTIONS[room_id];
            if(existedClient){
                if(existedClient === client){
                    logging.error('Connection UNEXPECTED closed: '+ room_id);
                    setTimeout(function(){createClients(room_id)}, parseInt(Math.random()*10000));
                }else{
                    logging.info('Connection closed by duplicated (EXPECTED): '+ room_id);
                }
            }
        }else{
            // logging.info('Client NORMAL Removed: '+ room_id);
        }
    };
    client.onopen = function() {
        sendJoinRoom(client, room_id);

        function sendHeartBeat(firstBeat) {
            if (client.readyState !== client.OPEN){return}

            if(firstBeat === true){
                client.send(HEART_BEAT);
                setTimeout(sendHeartBeat, 10000);
            }else{
                if(CURRENT_CONNECTIONS[room_id] !== client){
                    logging.error("Duplicated client! do not send heartbeat. room_id: " + room_id);
                    try{client.close()}catch(e){}
                }else{
                    if (ROOM_ID_POOL.has(room_id)){
                        client.send(HEART_BEAT);
                        setTimeout(sendHeartBeat, 10000);
                    }
                }
            }
        }
        sendHeartBeat(true);
        CURRENT_CONNECTIONS[room_id] = client;
        if (reconnectFlag){
            logging.info("Connection: " + room_id + " RECONNECTED!");
        }
    };
    client.onmessage = function(e) {
        parseMessage(e.data, room_id);
    };
}

(function (){
    let startProc = (roomList) => {
        logging.info("Rooms length: ", roomList.length);

        ROOM_ID_POOL.clear();
        for (let i = 0; i < roomList.length; i++){
            let room_id = roomList[i];
            let postfixnum = parseInt(room_id[room_id.length - 1]);
            if(postfixnum === PROC_NUMBER || postfixnum === (5 + PROC_NUMBER) || 1){
                ROOM_ID_POOL.add(parseInt(room_id));
            }
        }
        logging.info("ROOM_ID_POOL size: " + ROOM_ID_POOL.size);

        CURRENT_CONNECTIONS = {};
        ROOM_ID_POOL.forEach(function(room_id){
            setTimeout(function(){createClients(room_id)}, 1000*Math.random()*60);
        });

        setInterval(function (){
            logging.info(MESSAGE_COUNT + " messages received.");
            if (MESSAGE_COUNT > 999999999999){MESSAGE_COUNT = 0;}
        }, 1000*60);

        let intervalConnectionMonitor = function () {
            // 关闭不监控的
            let killedRooms = [];
            let currentRoomIds = Object.keys(CURRENT_CONNECTIONS);
            for (let i = 0; i < currentRoomIds.length; i++){
                let room_id = parseInt(currentRoomIds[i]);
                if(!ROOM_ID_POOL.has(room_id)){
                    killedRooms.push(room_id);
                    let client = CURRENT_CONNECTIONS[room_id];
                    delete CURRENT_CONNECTIONS[room_id];
                    if (client && client.readyState === client.OPEN){try{client.close()}catch(e){}}
                }
            }
            logging.info("Interval Connection Monitor: " + killedRooms.length + " connections removed.");

            // 重启要监控的
            let triggered = [];
            let monitorList = Array.from(ROOM_ID_POOL);
            for (let i = 0; i < monitorList.length; i++){
                let room_id = parseInt(monitorList[i]);
                let client = CURRENT_CONNECTIONS[room_id];
                if(client === undefined || client.readyState !== 1){
                    logging.debug("Client: " + client + "status: " + (client === undefined ? "-" : client.readyState));
                    delete CURRENT_CONNECTIONS[room_id];
                    triggered.push(room_id);
                    setTimeout(function(){createClients(room_id)}, parseInt(1000*Math.random()*60));
                }
            }
            logging.info("Interval Connection Monitor " + triggered.length + " connections triggered: " + triggered);
        };
        let updataRoomIdPool = () => {
            fs.readFile('./data/rooms.txt', "utf-8", (err, data) => {
                if (err) {
                    return
                }
                ROOM_ID_POOL.clear();
                let newRoomIdList = data.split("_");
                for (let i = 0; i < newRoomIdList.length; i++){
                    ROOM_ID_POOL.add(parseInt(newRoomIdList[i]))
                }
                logging.info("ROOM_ID_POOL update -> " + ROOM_ID_POOL.size);
            });
        };
        setInterval(intervalConnectionMonitor, 1000*60*2);
        setInterval(updataRoomIdPool, 1000*60*5);
    };

    fs.readFile('./data/rooms.txt', "utf-8", (err, data) => {
        if (err) {
            logging.error("Error happend when reading file, err: " + err.toString());
            return
        }
        startProc(data.split("_"));
    });
})();
