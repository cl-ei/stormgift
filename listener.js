let W3CWebSocket = require('websocket').w3cwebsocket;
let fs = require("fs");
let path = require('path');
let log4js = require('log4js');
let logger = require("./utils/logger");
let bilisocket = require("./utils/bilisocket");

let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");
let PROC_NUMBER = parseInt(sysArgs[1]) || 0;


let logging = logger.creatLogger('listener_' + PROC_NUMBER, DEBUG ? "./log/" : "/home/wwwroot/log/");
logging.info("Start proc -> proc num: " + PROC_NUMBER);

let MESSAGE_COUNT = 0;
let MESSAGE_INTERVAL_COUNT = 0;
let ROOM_ID_POOL = new Set();
let CURRENT_CONNECTIONS = {};

function procMessage(msg, room_id){
    MESSAGE_COUNT += 1;
    MESSAGE_INTERVAL_COUNT += 1;

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

    if(existedClient !== undefined){
        if(existedClient.readyState === 1) {
            logging.error("CODE ERROR! do not create duplicated client.");
            return
        }else{
            reconnectFlag = true;
            logging.info("Try reconnect to " + room_id);
        }
    }

    let client = new W3CWebSocket(bilisocket.MONITOR_URL);
    CURRENT_CONNECTIONS[room_id] = client;

    client.onerror = function() {
        client.onclose = undefined;
        let existedClient = CURRENT_CONNECTIONS[room_id];
        if (existedClient === undefined) {
            logging.error('Connection had removed. room id: ' + room_id);
        }else if (existedClient === client){
            logging.error('UNEXPECTED Connection Error happened, room id: ' + room_id);
            setTimeout(function(){createClients(room_id)}, Math.random()*10000)
        }else{
            logging.error('Connection Removed (EXPECTED, but caused by duplicated!), room id: ' + room_id);
        }
    };
    client.onopen = function() {
        bilisocket.sendJoinRoom(client, room_id);

        function sendHeartBeat() {
            if (client.readyState !== client.OPEN){return}
            if(CURRENT_CONNECTIONS[room_id] === client) {
                client.send(bilisocket.HEART_BEAT_PACKAGE);
                setTimeout(sendHeartBeat, 10000);
            }else{
                logging.error("Duplicated client! do not send heartbeat and shutdown. room_id: " + room_id);
                try{
                    client.onclose = undefined;
                    client.close()
                }catch(e){}
            }
        }
        sendHeartBeat();
        if (reconnectFlag){
            logging.info("Reconnected to " + room_id + " !");
        }
    };
    client.onclose = function() {
        logging.error("----- Connection CLOSED! Should not close... -----");
        // let existedClient = CURRENT_CONNECTIONS[room_id];
        // if(existedClient === undefined) {
        //     logging.info('Client UN-NORMAL Removed: '+ room_id);
        // }else{
        //     if(existedClient === client){
        //         logging.error('Connection UNEXPECTED closed: '+ room_id);
        //         // setTimeout(function(){createClients(room_id)}, Math.random()*10000)
        //     }else{
        //         logging.info('Connection closed by duplicated (EXPECTED): '+ room_id);
        //     }
        // }
    };
    client.onmessage = function(e) {
        bilisocket.parseMessage(e.data, room_id, procMessage);
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
            let mspeed = parseInt(MESSAGE_INTERVAL_COUNT/60.0);
            logging.info("Message counter: " +
                MESSAGE_INTERVAL_COUNT + " received, " +
                mspeed + " msg/s, " +
                MESSAGE_COUNT + " total."
            );
            if (MESSAGE_COUNT > 999999999999){MESSAGE_COUNT = 0;}
            MESSAGE_INTERVAL_COUNT = 0;
        }, 1000*60);

        let intervalConnectionMonitor = function () {
            // 关闭不监控的
            let killedRooms = [];
            let currentRoomIds = Object.keys(CURRENT_CONNECTIONS);
            for (let i = 0; i < currentRoomIds.length; i++){
                let room_id = parseInt(currentRoomIds[i]);
                if(!ROOM_ID_POOL.has(room_id)){
                    let client = CURRENT_CONNECTIONS[room_id];
                    if (client !== undefined && client.readyState === client.OPEN){
                        try{
                            client.onclose = undefined;
                            client.close()
                        }catch(e){
                            logging.error("An error occurred while attempting to close a connection: " + room_id + ", e:" + e.toString());
                        }
                        delete CURRENT_CONNECTIONS[room_id];
                        killedRooms.push(room_id);
                    }
                }
            }

            // 重启要监控的
            let triggered = [];
            let monitorList = Array.from(ROOM_ID_POOL);
            for (let i = 0; i < monitorList.length; i++){
                let room_id = parseInt(monitorList[i]);
                let client = CURRENT_CONNECTIONS[room_id];
                if(client === undefined){
                    triggered.push(room_id);
                    setTimeout(function(){createClients(room_id)}, parseInt(1000*Math.random()*60));
                }
            }
            logging.info(
                "ICM: current connection " + Object.keys(CURRENT_CONNECTIONS).length + " , " +
                killedRooms.length + " removed, " +
                triggered.length + " new triggered: " + triggered
            );
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
                logging.info(
                    "Update ROOM_ID_POOL: current connections: " + Object.keys(CURRENT_CONNECTIONS).length +
                    ", ID_POOL size: " + ROOM_ID_POOL.size
                );
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
