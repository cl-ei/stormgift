let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
let request = require("request");
let redis = require("redis");
let proj_config = require("../config/proj_config");
let env = proj_config.env;

let logging = require("../config/loggers").recorder;
logging.info("Start recorder proc.");


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

let UidAcquirer = {
    __ADMIN_WAY_LOCK: null,
    __getCookieCsrfTokenAnchorid: () => {
        let cookie_filename = '../data/cookie.js';
        let cookie = require(cookie_filename).RAW_COOKIE_LIST[0];

        let cookie_kv = cookie.split(";");
        let csrf_token = "";
        for (let i = 0; i < cookie_kv.length; i++){
            let kvstr = cookie_kv[i];
            if (kvstr.indexOf("bili_jct") > -1){
                csrf_token = kvstr.split("=")[1].trim();
                break;
            }
        }

        let anchor_id = 0;
        for (let i = 0; i < cookie_kv.length; i++){
            let kvstr = cookie_kv[i];
            if (kvstr.indexOf("DedeUserID") > -1){
                anchor_id = parseInt(kvstr.split("=")[1].trim());
                break;
            }
        }
        return [cookie, csrf_token, anchor_id];
    },
    ___getByAdminList_delAdminList: (name, FnWithOpenLock, cookie, csrf_token, anchor_id, uid) => {
        let delAdminReqParam = {
            url: "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/dismiss",
            method: "post",
            headers: {"User-Agent": UA, "Cookie": cookie},
            form: {
                uid: uid,
                csrf_token: csrf_token,
                csrf: csrf_token,
                visit_id: ""
            },
            timeout: 20000,
        };
        let onResponse = (err, res, body) => {
            if (err) {
                logging.error("Del admin error! e: %s", err.toString());
            }
            FnWithOpenLock();
        };
        request(delAdminReqParam, onResponse);
    },
    ___getByAdminList_getAdminList: (name, FnWithOpenLock, cookie, csrf_token, anchor_id) => {
        let reqParam = {
            url: "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/get_by_anchor?page=1",
            method: "get",
            headers: {"User-Agent": UA, "Cookie": cookie},
            timeout: 20000,
        };
        let onResponse = (err, res, body) => {
            let uid = null;
            if (err) {
                logging.error("read adminList error! e: %s", err.toString());
            }else {
                let r = {"-": "-"};
                try {
                    r = JSON.parse(body.toString());
                } catch (e) {
                    logging.error(
                        "Error response JSON, in ___getByAdminList_getAdminList. e: %s, body:\n-------\n%s\n\n",
                        e.toString(), body
                    );
                }
                let result = (r.data || {}).data || [];
                for (let i = 0; i < result.length; i++) {
                    if (result[i].uname === name) {
                        uid = result[i].uid;
                        break;
                    }
                }
            }

            if(uid === null) {
                FnWithOpenLock("Cannot add admin for user: " + name, null)
            }else{
                logging.info("Uid has been obtained by admin list, name: %s, uid: %s", name, uid);
                UidAcquirer.___getByAdminList_delAdminList(name, FnWithOpenLock, cookie, csrf_token, anchor_id, uid);
            }
        };
        request(reqParam, onResponse);
    },
    _getByAdminList: (name, Fn) => {
        let current = new Date().valueOf();
        if (UidAcquirer.__ADMIN_WAY_LOCK === null){
            UidAcquirer.__ADMIN_WAY_LOCK = current;
        }else{
            let lockTime = current - UidAcquirer.__ADMIN_WAY_LOCK;
            if(lockTime < 30*1000){
                logging.warn("_getByAdminList on locking! lockTime: %s", lockTime);
                setTimeout(() => {UidAcquirer._getByAdminList(name, Fn)}, 1000);
                return;
            }
            logging.info("Lock time too long. now open it. lockTime: %s", lockTime);
            UidAcquirer.__ADMIN_WAY_LOCK = current;
        }
        let FnWithOpenLock = (e, uid) => {
            logging.info("Get uid job done, cost time: %s ms.", (new Date().valueOf()) - UidAcquirer.__ADMIN_WAY_LOCK);
            UidAcquirer.__ADMIN_WAY_LOCK = null;
            Fn(e, uid);
        };

        let cca = UidAcquirer.__getCookieCsrfTokenAnchorid();
        let cookie = cca[0] || "";
        let csrf_token = cca[1] || "";
        let anchor_id = cca[2] || 0;
        if(cookie.length < 5 || csrf_token.length < 5 || !anchor_id){
            logging.error("When get uid by admin list find an error cookie!");
            return FnWithOpenLock("Error cookie", null);
        }

        let addAdminReqParam = {
            url: "https://api.live.bilibili.com/live_user/v1/RoomAdmin/add",
            method: "post",
            headers: {"User-Agent": UA, "Cookie": cookie},
            form: {
                admin: name,
                anchor_id: anchor_id,
                csrf_token: csrf_token,
                csrf: csrf_token,
                visit_id: ""
            },
            timeout: 20000,
        };
        let onAddAdminResponse = (err, res, body) => {
            logging.info("Get uid by Admin list: user has been added to admin list. name: %s", name);
            if (err) {
                logging.error("Add admin error! e: %s", err.toString());
            }
            UidAcquirer.___getByAdminList_getAdminList(name, FnWithOpenLock, cookie, csrf_token, anchor_id);
        };
        request(addAdminReqParam, onAddAdminResponse);
    },
    _getBySearch: (name, Fn) => {
        let reqParam = {
            url: encodeURI(
                "https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=" + name
            ),
            method: "get",
            headers: {"User-Agent": UA},
            timeout: 20000,
        };
        let onResponse = (err, res, body) => {
            if (err) {
                logging.error("Get User by name response Error, try other way. name: %s, e: %s", name, err.toString());
                UidAcquirer._getByAdminList(name, Fn);
                return;
            }
            let r = {"-": "-"};
            try {
                r = JSON.parse(body.toString());
            } catch (e) {
                logging.error("Error response JSON, try other way. e: %s, body:\n-------\n%s\n\n", e.toString(), body);
                UidAcquirer._getByAdminList(name, Fn);
                return;
            }
            if (r.code !== 0) {
                logging.error("Response code is not 0. try other way. code: %s, info: %s", r.code, r.message);
                UidAcquirer._getByAdminList(name, Fn);
                return;
            }
            let ulist = (r.data || {}).result || [];
            let uid = null;
            for (let i = 0; i < ulist.length; i++){
                if(ulist[i].uname === name){
                    uid = ulist[i].mid;
                    break;
                }
            }
            if (uid){
                logging.info("Uid obtained by search way, name: %s, uid: %s", name, uid);
                Fn(undefined, uid);
                return;
            }
            logging.warn("Uid can not get by search way, try other way. name: %s, uid: %s", name, uid);
            UidAcquirer._getByAdminList(name, Fn);
        };
        request(reqParam, onResponse);
    },
    getUidByName: (name, Fn) => {
        UidAcquirer._getBySearch(name, Fn)
    }
};


let Parser = {
    cookieDictList: [],

    __ROOM_ID_POOL: [],
    __getTVGiftIdTask: 0,

    __INVALID_PRIZE_POOL: [],
    __checkGiftAvailable: (k) => {
        let r = Parser.__INVALID_PRIZE_POOL.indexOf(k) < 0;
        if(r){
            Parser.__INVALID_PRIZE_POOL.push(k);
            while(Parser.__INVALID_PRIZE_POOL.length > 2000){
                Parser.__INVALID_PRIZE_POOL.shift();
            }
        }
        return r;
    },
    parse: (room_id) => {
        if (Parser.__ROOM_ID_POOL.indexOf(room_id) < 0) {
            Parser.__ROOM_ID_POOL.push(room_id);
            if (Parser.__getTVGiftIdTask === 0) {
                Parser.__getTVGiftIdTask = setInterval(Parser.__getTVGiftId, 1000);
            }
        }
    },
    __getTVGiftId: () => {
        let room_id = Parser.__ROOM_ID_POOL.shift();
        if(Parser.__ROOM_ID_POOL.length === 0 && Parser.__getTVGiftIdTask !== 0){
            clearInterval(Parser.__getTVGiftIdTask);
            Parser.__getTVGiftIdTask = 0;
        }

        let reqParam = {
            url: "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA},
            timeout: 20000,
        },
        cbFn = (err, res, body) => {
            if (err) {
                logging.error("Get tv gift id error: %s, room_id: %s", err.toString(), room_id);
                return;
            }
            let r = {"-": "-"};
            try {
                r = JSON.parse(body.toString());
            } catch (e) {
                logging.error("Error response getTvGiftId: %s, body:\n-------\n%s\n\n", e.toString(), body);
                return;
            }
            let gidList = (r.data || {}).list || [];

            let procDist = {};
            for (let i = 0; i < gidList.length; i++) {
                let gidObject = gidList[i];

                let gift_id = parseInt(gidObject.raffleId) || 0;
                let key = "_T" + room_id + "$" + gift_id;
                if (Parser.__checkGiftAvailable(key)){
                    gidObject.room_id = room_id;
                    gidObject.created_time = getLocalTimeStr();

                    let username = gidObject.from;
                    if (username in procDist){
                        procDist[username].push(gidObject)
                    }else{
                        procDist[username] = [gidObject]
                    }
                }
            }
            let user_names = Object.keys(procDist);
            for(let i = 0; i < user_names.length; i++){
                let name = user_names[i];
                setTimeout(() => {Parser.__recordByUser(name, procDist[name])}, 500*(i+1));
            }
        };
        logging.info("Send request for getting guard gift id, room_id: %s", room_id);
        request(reqParam, cbFn);
    },
    __recordByUser: (name, giftList) => {
        logging.debug("__recordByUser, name: %s, gift list: %s", name, giftList.length);

        let callback = (e, uid) => {
            if(e){
                logging.error("Cannot get uid by name: %s, e: %s", name, e);
                uid = null;
            }
            for (let i = 0; i < giftList.length; i++){
                let info = giftList[i];
                let gift_id = info.raffleId;
                let room_id = info.room_id;
                let key = "_T" + room_id + "$" + gift_id;

                let savedData = JSON.stringify({
                    uid: uid,
                    name: name,
                    face: info.from_user.face,
                    room_id: room_id,
                    gift_id: gift_id,
                    gift_name: info.title,
                    gift_type: info.type,
                    sender_type: info.sender_type,
                    created_time: info.created_time,
                    status: info.status
                });

                DataAccess.nonRepetitiveExecute(key, savedData, () => {
                    logging.info("Tv gift info saved, key: %s, data: %s", key, savedData);
                });
            }
        };
        UidAcquirer.getUidByName(name, callback);
    }
};


let Receiver = {
    connectToNoticeServer: () => {
        let W3CWebSocket = require('websocket').w3cwebsocket;
        let client = new W3CWebSocket(env === "server" ? "ws://127.0.0.1:11112" : "ws://129.204.43.2:11112");
        client.onerror = () => {
            logging.error("Connection to notice server error! Try reconnect...");
            client.onclose = undefined;
            setTimeout(Receiver.connectToNoticeServer, 500);
        };
        client.onopen = () => {
            logging.info("Receiver started.");
            function sendHeartBeat() {
                if (client.readyState === client.OPEN){
                    client.send("HEARTBEAT");
                    setTimeout(sendHeartBeat, 10000);
                }
            }
            sendHeartBeat();
        };
        client.onclose = () => {
            logging.error("ConnectToNoticeServer closed! Try reconnect...");
            setTimeout(Receiver.connectToNoticeServer, 500);
        };
        client.onmessage = (e) => {
            let mList = e.data.match(/(_T|_G|XG|_S|NG)\d{2,}\$?\d+/g) || [];
            for(let i = 0; i < mList.length; i++){
                let msg = mList[i];
                let source = msg[0];
                let giftType = msg[1];
                let msgBody = msg.slice(2);
                if(giftType === "T"){
                    let room_id = parseInt(msgBody);
                    logging.info("Receiver: Gift: %s, room_id: %s", giftType, room_id);
                    Parser.parse(room_id);
                }
            }
        };
    },
    init: () => {
        Receiver.connectToNoticeServer();
    }
};


DataAccess.init();
Receiver.init();
