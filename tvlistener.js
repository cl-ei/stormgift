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

let AREA_NAME_MAP = {
    0: "全区",
    1: "娱乐",
    2: "游戏",
    3: "手游",
    4: "绘画",
    5: "电台",
};

let BiliAPI = {
    headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    },
    searchNewRoomId: (area, old_room_id, cbFn) => {
        let url = "https://api.live.bilibili.com/room/v3/area/getRoomList?platform=web&cate_id=0&area_id=0&sort_type=&page=1&page_size=10&parent_area_id=" + area;
        request({
            url: url,
            method: "get",
            headers: BiliAPI.headers,
            timeout: 10000,
        },function (err, res, body) {
            let newRoomId = 0,
                result = false;
            if(err){
                logging.error("Error happened in searchNewRoomId, area: %s, room_id: %s, err: %s", area, err.toString());
            }else{
                try{
                    let list = JSON.parse(body.toString()).data.list;
                    for(let i = 0; i < list.length; i++){
                        let room_id = parseInt(list[i].roomid);
                        if(room_id && room_id !== old_room_id){
                            newRoomId = room_id;
                            break;
                        }
                    }
                }catch (e) {
                    newRoomId = 0;
                    logging.info("Get new room id error! area: %s, e: %s", area, e.toString());
                }
                if(newRoomId !== 0){
                    logging.info("Found new room id: %s, area: %s", newRoomId, AREA_NAME_MAP[area]);
                    result = true;
                }
            }
            cbFn(result, area, newRoomId);
        })
    },
    checkStatus: (area, room_id, cbFn) => {
        if(room_id === undefined || !room_id){cbFn(false, area, room_id); return;}

        request({
            url: "https://api.live.bilibili.com/AppRoom/index?platform=android&room_id=" + room_id,
            method: "get",
            headers: BiliAPI.headers,
            timeout: 10000,
        },function (err, res, body) {
            let result = false;
            if(err){
                logging.error(
                    "Error happened in checkStatus, area: %s, room_id: %s, err: %s",
                    AREA_NAME_MAP[area], room_id, err.toString()
                );
            }else {
                let data = (JSON.parse(body.toString()) || {}).data || {};
                if (data.status === "LIVE" && data.area_v2_parent_id === area) {
                    result = true;
                }
            }
            cbFn(result, area, room_id)
        })
    },
};

let MessageCounter = {
    MESSAGE_COUNT: 0,
    MESSAGE_INTERVAL_COUNT: 0,
    __interValSec: 60,

    printMessageSpeed: () => {
        let mspeed = parseInt(MessageCounter.MESSAGE_INTERVAL_COUNT/60.0);
        logging.info(
            "Message counter: %d received, %s msg/s, %s total.",
            MessageCounter.MESSAGE_INTERVAL_COUNT, mspeed, MessageCounter.MESSAGE_COUNT
        );
        if (MessageCounter.MESSAGE_COUNT > 999999999999){MessageCounter.MESSAGE_COUNT = 0}
        MessageCounter.MESSAGE_INTERVAL_COUNT = 0;
    },
    add: () => {
        MessageCounter.MESSAGE_COUNT += 1;
        MessageCounter.MESSAGE_INTERVAL_COUNT += 1;
    },
    init: (seconds) => {
        seconds = seconds || 60;
        MessageCounter.__interValSec = seconds;
        setInterval(MessageCounter.printMessageSpeed, seconds*1000)
    }
};

let NoticeSender = {
    PRIZE_NOTICE_HOST: DEBUG ? "111.230.235.254" : "localhost",
    PRIZE_NOTICE_PORT: 11111,

    __noticeSenderList: [],
    __genNoticeSender: () => {
        let c = new net.Socket();
        c.on("error", () => {
            // logging.error("Error happened in prizeNoticeClient.");
            c.destroy();
        });
        c.on('data', (data) => {
            logging.info('Client received: ' + data);
        });
        c.on('close', () => {
            logging.error('Connection closed! Unexpected!');
            while(NoticeSender.__noticeSenderList.pop() !== undefined){}
            setTimeout(NoticeSender.__genNoticeSender, 500);
        });
        c.connect(NoticeSender.PRIZE_NOTICE_PORT, NoticeSender.PRIZE_NOTICE_HOST, () => {
            logging.info("PrizeNoticeClient connected.");
            NoticeSender.__noticeSenderList.push(c);
        });
    },
    sendMsg: (message) => {
        if(DEBUG){console.log("SEND: %s", message);return;}
        if(NoticeSender.__noticeSenderList.length > 0){
            if (NoticeSender.__noticeSenderList[0].write(message) !== true){
                logging.error("Prize message send failed: %s", message);
            }
        }else{
            logging.info("No prize sender: %s", message);
        }
    },
    init: () => {
        if(!DEBUG){
            NoticeSender.__genNoticeSender();
        }
    }
};

let TVMonitor = {
    CURRENT_CONNECTIONS: {},
    ROOM_AREA_MAP: {
        0: 2516117
    },
    WS_CONNECTION_UPDATING: false,

    getAreaNameByRoomId: (room_id) => {
        for (let area = 0; area <= 5; area++){
            if (TVMonitor.ROOM_AREA_MAP[area] === room_id){
                return area;
            }
        }
        return -1;
    },
    procMessage: (msg, room_id) => {
        MessageCounter.add();
        if(msg.cmd === "NOTICE_MSG"){
            if (msg.msg_type !== 2){return}

            let area = TVMonitor.getAreaNameByRoomId(room_id),
                message = msg.msg_self;
            let broadcastType = message.slice(0, 5);
            if (broadcastType.indexOf(AREA_NAME_MAP[area]) > -1){
                let real_room_id = parseInt(msg.real_roomid) || 0;
                if(real_room_id !== 0){
                    logging.info(
                        "TV_PRIZE: %s, area: %s, room_id: %s",
                        message, AREA_NAME_MAP[area], real_room_id
                    );
                    NoticeSender.sendMsg("_T" + real_room_id);
                }
            }
        }else if(msg.cmd === "PREPARING"){
            let area = TVMonitor.getAreaNameByRoomId(room_id);
            logging.info("Room closed! prepare to search new. room_id: %s, area: %s.", room_id, AREA_NAME_MAP[area]);
            TVMonitor.updateMonitorRooms([area]);
        }
    },
    createClients: (room_id) => {
        let existedClient = TVMonitor.CURRENT_CONNECTIONS[room_id],
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
        TVMonitor.CURRENT_CONNECTIONS[room_id] = client;

        client.onerror = () => {logging.error("Client error!")};
        client.onopen = () => {
            bilisocket.sendJoinRoom(client, room_id);

            let sendHeartBeat = () => {
                if (client.readyState !== client.OPEN){return}
                if(TVMonitor.CURRENT_CONNECTIONS[room_id] === client) {
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
            if (reconnectFlag){logging.info("%d reconnected!", room_id)}
        };
        client.onclose = () => {
            let existedClient = TVMonitor.CURRENT_CONNECTIONS[room_id];
            if (existedClient === undefined) {
                logging.error('Connection had closed. room id: ' + room_id);
            }else if (existedClient === client){
                logging.error('UNEXPECTED Connection Error happened, room id: ' + room_id);
                setTimeout(() => {TVMonitor.createClients(room_id)}, 1000)
            }else{
                logging.error('Connection Removed (EXPECTED, but caused by duplicated!), room id: ' + room_id);
            }
        };
        client.onmessage = (e) => {bilisocket.parseMessage(e.data, room_id, TVMonitor.procMessage)};
    },
    __updateWSConnection: () => {
        if(TVMonitor.WS_CONNECTION_UPDATING){
            logging.warn("__updateWSConnection BUSY!");
            setTimeout(TVMonitor.__updateWSConnection, 200);
            return;
        }
        TVMonitor.WS_CONNECTION_UPDATING = true;

        // 关闭不监控的
        let killedRooms = [];
        let currentRoomIds = Object.keys(TVMonitor.CURRENT_CONNECTIONS),
            distRoomIds = Object.values(TVMonitor.ROOM_AREA_MAP);
        for (let i = 0; i < currentRoomIds.length; i++){
            let room_id = parseInt(currentRoomIds[i]);

            if(distRoomIds.indexOf(room_id) < 0){  // not in distRoomIds
                let client = TVMonitor.CURRENT_CONNECTIONS[room_id];
                if (client !== undefined && client.readyState === client.OPEN){
                    try{
                        client.onclose = undefined;
                        client.close()
                    }catch(e){
                        logging.error("An error occurred while attempting to close a connection: " + room_id + ", e:" + e.toString());
                    }
                    delete TVMonitor.CURRENT_CONNECTIONS[room_id];
                    killedRooms.push(room_id);
                }
            }
        }

        // 启动要监控的
        let triggered = [];
        for (let i = 0; i < distRoomIds.length; i++){
            let room_id = parseInt(distRoomIds[i]);
            if(room_id === 0 || room_id === undefined){
                continue;
            }
            let client = TVMonitor.CURRENT_CONNECTIONS[room_id];
            if(client === undefined){
                triggered.push(room_id);
                TVMonitor.createClients(room_id);
            }
        }
        logging.info(
            "Websocket connection updated: removed: %s, new triggered: %s.",
            killedRooms.length ? killedRooms : "-", triggered.length ? triggered : "-"
        );
        TVMonitor.WS_CONNECTION_UPDATING = false;
    },
    updateMonitorRooms: (areaList) => {
        areaList = areaList || [1, 2, 3, 4, 5];
        for (let i = 0; i < areaList.length; i++){
            let area = areaList[i];
            setTimeout(() => {
                BiliAPI.checkStatus(area, TVMonitor.ROOM_AREA_MAP[area], (status, area, room_id) => {
                    if(status === true){return}
                    if(room_id !== undefined){
                        logging.error("Room %s from area %s closed! search new...", room_id, AREA_NAME_MAP[area]);
                    }
                    BiliAPI.searchNewRoomId(area, room_id, (result, area, newRoomId) => {
                        if (!result){return}
                        TVMonitor.ROOM_AREA_MAP[area] = parseInt(newRoomId);
                        TVMonitor.__updateWSConnection()
                    })
                });
            }, 500*i);
        }
    },
    printConnectionInfo: () => {
        let currentRoomIds = [],
            distRoomIds = Object.values(TVMonitor.ROOM_AREA_MAP),
            aliveWS = [],
            needDel = [],
            needTriggered = [],
            c = Object.keys(TVMonitor.CURRENT_CONNECTIONS);

        for (let i = 0; i < c.length; i++){
            currentRoomIds.push(parseInt(c[i]))
        }

        for (let i = 0; i < currentRoomIds.length; i++){
            let room_id = currentRoomIds[i];
            if (distRoomIds.indexOf(room_id) < 0){needDel.push(room_id)}
            let client = TVMonitor.CURRENT_CONNECTIONS[room_id];
            if (client && client.readyState === client.OPEN){
                aliveWS.push(room_id);
            }
        }

        for (let i = 0; i < distRoomIds.length; i++){
            let room_id = distRoomIds[i];
            if(currentRoomIds.indexOf(room_id) < 0){
                needTriggered.push(room_id);
            }
        }
        logging.info(
            "WS INFO: current cnt: %s, connected: %s, need del: %s, need triggered: %s.",
            aliveWS.length, aliveWS, needDel.length ? needDel : "-", needTriggered.length ? needTriggered : "-"
        )
    },
    init: () => {
        TVMonitor.updateMonitorRooms();
        setInterval(TVMonitor.updateMonitorRooms, 120*1000);
        setInterval(TVMonitor.printConnectionInfo, 130*1000);
    }
};


(() => {
    MessageCounter.init();
    NoticeSender.init();
    TVMonitor.init();
})();
