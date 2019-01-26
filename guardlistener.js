let proj_config = require("./config/proj_config");
let env = proj_config.env;

let request = require("request");
let redis = require('redis');
let net = require('net');
let logging = require("./config/loggers").guardlistener;
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";


let getLocalTimeStr = () => {
    let unixtimestamp = new Date();
    let year = 1900 + unixtimestamp.getYear();
    let month = "0" + (unixtimestamp.getMonth() + 1);
    let date = "0" + unixtimestamp.getDate();
    let hour = "0" + unixtimestamp.getHours();
    let minute = "0" + unixtimestamp.getMinutes();
    let second = "0" + unixtimestamp.getSeconds();
    let result = year +
        "-" + month.substring(month.length - 2, month.length) +
        "-" + date.substring(date.length - 2, date.length) +
        " " + hour.substring(hour.length - 2, hour.length) +
        ":" + minute.substring(minute.length - 2, minute.length) +
        ":" + second.substring(second.length - 2, second.length);
    return result;
};


let DataAccess = {
    redis_client: undefined,
    nonRepetitiveExecute: (key, data, cbFn) => {
        if (DataAccess.redis_client === undefined){
            setTimeout(() => {DataAccess.nonRepetitiveExecute(key, cbFn)}, 500);
            return;
        }
        DataAccess.redis_client.set(key, data, "ex", 3600*24*7, "nx", (e, d) => {
            if(e){
                logging.error("Redis set error! %s, key: %s, data: %s", e, key, data);
                cbFn();
                return;
            }
            if(d){
                logging.info("Guard info saved, key: %s", key);
                cbFn();
            }
        });
    },
    init: () => {
        let rc = redis.createClient(
            proj_config.redis.port,
            proj_config.redis.host,
            {auth_pass: proj_config.redis.auth_pass, db: proj_config.redis.db}
        );
        rc.on('connect',function(){
            DataAccess.redis_client = rc;
            console.log('Redis client connected.');
        });
    }
};
let NoticeSender = {
    PRIZE_NOTICE_HOST: "localhost",
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
        if(env !== "server"){console.log("SEND: %s", message);return;}
        if(NoticeSender.__noticeSenderList.length > 0){
            if (NoticeSender.__noticeSenderList[0].write(message) !== true){
                logging.error("Prize message send failed: %s", message);
            }
        }else{
            logging.info("No prize sender: %s", message);
        }
    },
    init: () => {
        if(env === "server"){
            NoticeSender.__genNoticeSender();
        }
    }
};
let GuardListener = {
    GUARD_ROOM_ID_LIST: [],
    GET_GID_DISPATCHER_TASK_ID: 0,
    getSingleGid: (room_id) => {
        let reqParam = {
            url: "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA},
            timeout: 20000,
        },
        cbFn = (err, res, body) => {
            if (err) {
                logging.error("Get guard gift id error: %s, room_id: %s", err.toString(), room_id);
                return;
            }
            let r = {"-": "-"};
            try {
                r = JSON.parse(body.toString());
            } catch (e) {
                logging.error("Error response getTvGiftId: %s, body:\n-------\n%s\n\n", e.toString(), body);
                return;
            }
            if (r.code !== 0) {return}

            let gidList = r.data || [];
            for (let i = 0; i < gidList.length; i++) {
                let giftInfo = gidList[i];
                let gift_id = parseInt(giftInfo.id);
                let savedData = JSON.stringify({
                    uid: giftInfo.sender.uid,
                    name: giftInfo.sender.uname,
                    face: giftInfo.sender.face,
                    room_id: room_id,
                    gift_id: gift_id,
                    gift_name: "guard",
                    gift_type: "G" + giftInfo.privilege_type,
                    sender_type: null,
                    created_time: getLocalTimeStr(),
                    status: giftInfo.status
                });
                let k = "NG" + room_id + "$" + gift_id;
                DataAccess.nonRepetitiveExecute(k, savedData, () => {NoticeSender.sendMsg(k)});
            }
        };
        logging.info("Send getting guard gift id request, room_id: %s", room_id);
        request(reqParam, cbFn);
    },
    getGidDispatcher: () => {
        let room_id = GuardListener.GUARD_ROOM_ID_LIST.shift();
        if(GuardListener.GUARD_ROOM_ID_LIST.length === 0 && GuardListener.GET_GID_DISPATCHER_TASK_ID !== 0){
            clearInterval(GuardListener.GET_GID_DISPATCHER_TASK_ID);
            GuardListener.GET_GID_DISPATCHER_TASK_ID = 0;
        }
        GuardListener.getSingleGid(room_id);
    },
    getGuardList: () => {
        request({
            url: "https://dmagent.chinanorth.cloudapp.chinacloudapi.cn:23333/Governors/View",
            method: "get",
            headers: {"User-Agent": UA},
            timeout: 10000,
        },function (err, res, body) {
            if(err){
                logging.error("Error happened: %s, r: %s", err.toString(), body.toString());
                return;
            }
            let response = body.toString();
            if (response.indexOf("提督列表") < 0 || response.indexOf("舰长列表") < 0){
                logging.error("Response data error! r: %s", body.toString());
                return;
            }

            let totallist = response.match(/live.bilibili.com\/(\d+)/g) || [];
            logging.info("Get guard list success, length: %s.", totallist.length);

            for (let i = 0; i < totallist.length; i++){
                let url = totallist[i];
                let room_id = parseInt(url.match(/\d+/g)[0]);
                if(GuardListener.GUARD_ROOM_ID_LIST.indexOf(room_id) < 0){
                    GuardListener.GUARD_ROOM_ID_LIST.push(room_id);
                }
            }
            if (GuardListener.GUARD_ROOM_ID_LIST.length > 0 && GuardListener.GET_GID_DISPATCHER_TASK_ID === 0){
                GuardListener.GET_GID_DISPATCHER_TASK_ID = setInterval(GuardListener.getGidDispatcher, 250);
                logging.info("GuardListener.getGidDispatcher started.");
            }
        })
    },
    init: () => {
        setInterval(GuardListener.getGuardList, 6*60*1000);
        GuardListener.getGuardList();
    },
};


NoticeSender.init();
DataAccess.init();
GuardListener.init();
