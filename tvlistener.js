let W3CWebSocket = require('websocket').w3cwebsocket;
let logger = require("./utils/logger");
let bilisocket = require("./utils/bilisocket");
let net = require('net');
let request = require("request");

let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let loggerFilePath = DEBUG ? "./log" : "/home/wwwroot/log";
let logging = logger.creatLogger("tvlistener", loggerFilePath);

logging.info("Start TV Listener proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));

let PRIZE_NOTICE_HOST = DEBUG ? "111.230.235.254" : "localhost";
let PRIZE_NOTICE_PORT = 11111;
let __prizeSenderList = [];
let sendPrizeMessage = (message) => {
    if(__prizeSenderList.length > 0){
        if (__prizeSenderList[0].write(message) !== true){
            logging.error("Prize message send failed: %s", message);
        }
    }else{
        logging.info("Default prize sender: %s", message);
    }
};
let __generateNoticeSender = () => {
    let __prizeNoticeClient = new net.Socket();
    __prizeNoticeClient.on("error", () => {
        // logging.error("Error happened in prizeNoticeClient.");
        __prizeNoticeClient.destroy();
    });
    __prizeNoticeClient.on('data', (data) => {
        logging.info('Client received: ' + data);
    });
    __prizeNoticeClient.on('close', () => {
        logging.error('Connection closed! Unexpected!');
        while(__prizeSenderList.pop() !== undefined){}
        setTimeout(__generateNoticeSender, 500);
    });
    let onConnected = () => {
        logging.info("PrizeNoticeClient connected.");
        __prizeSenderList.push(__prizeNoticeClient);
    };
    __prizeNoticeClient.connect(PRIZE_NOTICE_PORT, PRIZE_NOTICE_HOST, onConnected);
};
__generateNoticeSender();


let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
let headers = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
};
let MESSAGE_COUNT = 0;
let MESSAGE_INTERVAL_COUNT = 0;
let CURRENT_CONNECTIONS = {};
let ROOM_AREA_MAP = {
    0: 2516117,
};


let getRoomIdArea = (room_id) => {
    for (let area = 0; area <= 5; area++){
        if (ROOM_AREA_MAP[area] === room_id){
            return area;
        }
    }
    return -1;
};
let AREA_NAME_MAP = {
    0: "全区",
    1: "娱乐",
    2: "游戏",
    3: "手游",
    4: "绘画",
    5: "电台",
};

let procMessage = (msg, room_id) => {
    MESSAGE_COUNT += 1;
    MESSAGE_INTERVAL_COUNT += 1;

    if(msg.cmd === "NOTICE_MSG"){
        if (msg.msg_type !== 2){return}

        let area = getRoomIdArea(room_id),
            message = msg.msg_self;
        let broadcastType = message.slice(0, 5);
        if (broadcastType.indexOf(AREA_NAME_MAP[area]) > -1){
            let real_room_id = parseInt(msg.real_roomid) || 0;
            if(real_room_id !== 0){
                logging.info("TV_PRIZE: %s, area: %s, room_id: %s", message, AREA_NAME_MAP[area], real_room_id);
                sendPrizeMessage("_T" + real_room_id);
            }
        }
    }
};
let createClients = (room_id) => {
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

    client.onerror = () => {logging.error("Client error!")};
    client.onopen = () => {
        bilisocket.sendJoinRoom(client, room_id);

        let sendHeartBeat = () => {
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
        };
        sendHeartBeat();
        if (reconnectFlag){logging.info("Reconnected to " + room_id + " !")}
    };
    client.onclose = () => {
        let existedClient = CURRENT_CONNECTIONS[room_id];
        if (existedClient === undefined) {
            logging.error('Connection had closed. room id: ' + room_id);
        }else if (existedClient === client){
            logging.error('UNEXPECTED Connection Error happened, room id: ' + room_id);
            setTimeout(() => {createClients(room_id)}, Math.random()*10000)
        }else{
            logging.error('Connection Removed (EXPECTED, but caused by duplicated!), room id: ' + room_id);
        }
    };
    client.onmessage = (e) => {bilisocket.parseMessage(e.data, room_id, procMessage)};
};

let printMessageSpeed = () => {
    let room_id_list = Object.keys(CURRENT_CONNECTIONS),
        livedRooms = [];
    for (let i = 0; i < room_id_list.length; i++){
        let room_id = room_id_list[i];
        if (CURRENT_CONNECTIONS[room_id] === undefined){
            logging.error("Room %s DISCONNECTED!", room_id);
        }else if(CURRENT_CONNECTIONS[room_id].readyState !== 1){
            logging.error("Room %s readyStatus(%s) Error!", room_id, CURRENT_CONNECTIONS[room_id].readyState);
        }else{
            livedRooms.push(room_id)
        }
    }

    let mspeed = parseInt(MESSAGE_INTERVAL_COUNT/60.0);
    logging.info("Message counter: " +
        MESSAGE_INTERVAL_COUNT + " received, " +
        mspeed + " msg/s, " +
        MESSAGE_COUNT + " total, " +
        "websocket connected rooms: " + livedRooms
    );
    if (MESSAGE_COUNT > 999999999999){MESSAGE_COUNT = 0;}
    MESSAGE_INTERVAL_COUNT = 0;
};
let intervalConnectionMonitor = function () {
    // 关闭不监控的
    let killedRooms = [];
    let currentRoomIds = Object.keys(CURRENT_CONNECTIONS),
        distRoomIds = Object.values(ROOM_AREA_MAP);
    for (let i = 0; i < currentRoomIds.length; i++){
        let room_id = parseInt(currentRoomIds[i]);
        if(distRoomIds.indexOf(room_id) < 0){  // not in
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
    for (let i = 0; i < distRoomIds.length; i++){
        let room_id = parseInt(distRoomIds[i]);
        if(room_id === 0 || room_id === undefined){
            continue;
        }
        let client = CURRENT_CONNECTIONS[room_id];
        if(client === undefined){
            triggered.push(room_id);
            createClients(room_id);
        }
    }
    logging.info(
        "ICM: current connection " + Object.keys(CURRENT_CONNECTIONS).length + ", " +
        "ROOM_AREA_MAP size " + distRoomIds.length + ", " +
        killedRooms.length + " removed, " +
        triggered.length + " new triggered."
    );
};

let searchMonitorRoom = () => {
    logging.info("Start to search and check monitor room.");

    let searchSingleArea = (area, room_id) => {
        let searchNewRoom = (area) => {
            let url = "https://api.live.bilibili.com/room/v3/area/getRoomList?platform=web&cate_id=0&area_id=0&sort_type=&page=1&page_size=10&parent_area_id=" + area;
            request({
                url: url,
                method: "get",
                headers: headers,
                timeout: 10000,
            },function (err, res, body) {
                if(err){
                    logging.error(
                        "Error happened in searchNewRoom, area: %s, room_id: %s, err: %s",
                        AREA_NAME_MAP[area], err.toString()
                    );
                }else{
                    let response = JSON.parse(body.toString());
                    if (response.code !== 0){
                        logging.error(
                            "Get area %s live room id failed! r: %s",
                            AREA_NAME_MAP[area], JSON.stringify(response)
                        );
                        return;
                    }
                    let newRoomId = 0;
                    try{newRoomId = parseInt(response.data.list[0].roomid) || 0;}catch (e) {
                        console.log("Get new room id error! area: %s, e: %s",
                            AREA_NAME_MAP[area],
                            e.toString()
                        );
                        return;
                    }
                    if(newRoomId !== 0){
                        logging.info("Found new room id: %s, area: %s", newRoomId, AREA_NAME_MAP[area]);
                        ROOM_AREA_MAP[area] = newRoomId;
                    }
                }
            });

        };
        if (room_id === undefined || !room_id){
            logging.warn("Invalid room id: %d of area %s, search new.", room_id, AREA_NAME_MAP[area]);
            return searchNewRoom(area);
        }
        let url = "https://live.bilibili.com/" + room_id;
        request({
            url: url,
            method: "get",
            headers: headers,
            timeout: 10000,
        },function (err, res, body) {
            if(err){
                logging.error("Error happened in searchSingleArea, area: %s, room_id: %s, err: %s", area, room_id, err.toString());
            }else{
                let room_still_available = true;
                if(body.indexOf('"live_status":1') > -1){
                    if(body.indexOf('"parent_area_name":"' + AREA_NAME_MAP[area]) > -1){
                        logging.info("Room %s from area %s is still lived!", room_id, AREA_NAME_MAP[area]);
                    }else{
                        logging.error("Room %s has changed area! origin area %s.", room_id, AREA_NAME_MAP[area]);
                        room_still_available = false;
                    }
                }else{
                    logging.error("Room %s closed. now search new room, area: %s", room_id, AREA_NAME_MAP[area]);
                    room_still_available = false;
                }
                if(!room_still_available){
                    return searchNewRoom(area);
                }
            }
        })
    };
    for (let i = 1; i <= 5; i++){
        let old_room_id = parseInt(ROOM_AREA_MAP[i]) || 0;
        searchSingleArea(i, old_room_id);
    }
};

(function (){
    searchMonitorRoom();
    setInterval(printMessageSpeed, 1000*60);
    setTimeout(function(){
        logging.info("Start monitor, current rooms: %s", JSON.stringify(ROOM_AREA_MAP));
        intervalConnectionMonitor();

        setInterval(searchMonitorRoom, 1000*60*3);
        setInterval(intervalConnectionMonitor, 1000*60*2);
    }, 1000*10);
})();
