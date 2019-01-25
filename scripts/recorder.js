let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
let request = require("request");
let proj_config = require("../config/proj_config");
let env = proj_config.env;

let logging = require("../config/loggers").recorder;
logging.info("Start tvrecorder proc.");


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
    connection: undefined,
    init: () => {
        let mysql = require('mysql');
        let connection = mysql.createConnection(proj_config.mysql);
        connection.connect(function (err) {
            if (err) {
                let msg = "Mysql cannot connect! e: %s" + err;
                logging.error(msg);
                throw msg;
            }
            DataAccess.connection = connection;
            logging.info("Mysql connected.");
        })
    },
    updateUser: (id, data, Fn) => {
        logging.debug("Update user, id: %s, data: %s", id, JSON.stringify(data));
        let sql = 'update user set uid=?, name=?, face=? where id=?';
        DataAccess.connection.query(sql, [data.uid, data.name, data.face, id], (err, rows, fields) => {
            if (err) {
                let msg = "Mysql createUser error! e: %s" + err;
                logging.error(msg);
                return ;
            }
            logging.info("User has been updated, id: %s, uid: %s, name: %s", id, data.uid, data.name);
            Fn(id);
        });
    },
    createUser: (uid, name, face, Fn) => {
        logging.debug("Creating user... uid: %s, name: %s", uid, name);
        if (uid === null || uid === undefined || uid < 1){
            uid = null;
        }
        let sql = 'insert into user(uid, name, face) values(?, ?, ?)';
        DataAccess.connection.query(sql, [uid, name, face], (err, rows, fields) => {
            if (err) {
                let msg = "Mysql createUser error! e: %s" + err;
                logging.error(msg);
                return ;
            }
            logging.debug("User has been created. id: %s, uid: %s, name: %s", rows.insertId, uid, name);
            Fn(rows.insertId);
        });
    },
    getUserByUid: (uid, name, face, Fn) => {
        logging.debug("Now try to get user ByUid, uid: %s, name: %s", uid, name);

        let sql = "select * from user where uid = ? limit 1";
        DataAccess.connection.query(sql, [uid], (err, rows, fields) => {
            if (err) {
                let msg = "Mysql query error! e: %s" + err;
                logging.error(msg);
                return ;
            }
            if(rows && rows.length > 0){
                let u = rows[0];
                if(u.name === name){
                    logging.debug("User has been obtained by uid, uid: %s, name: %s", uid, name);
                    Fn(u.id);
                }else{
                    logging.debug("User need update, uid: %s, name: %s, old_name: %s", uid, name, u.name);
                    DataAccess.updateUser(u.id, {uid: uid, name: name, face: face}, Fn);
                }
            }else{
                logging.warn("Cannot get user just by uid, try get by name. uid: %s", uid);
                sql = "select * from user where uid is NULL and name = ? limit 1";
                DataAccess.connection.query(sql, [name], (err, rows, fields) => {
                    if (err) {
                        let msg = "Mysql query error! e: %s" + err;
                        logging.error(msg);
                        return ;
                    }
                    if(rows && rows.length > 0){
                        let u = rows[0];
                        logging.info("User has been obtained by name, name: %s, id: %s. now update its uid.", u.name, u.id);
                        DataAccess.updateUser(u.id, {uid: uid, name: name, face: face}, Fn);
                    }else{
                        logging.info("Cannot get user by uid and name, now create one. uid: %s, name: %s", uid, name);
                        DataAccess.createUser(uid, name, face, Fn);
                    }
                })
            }
        })
    },
    getUserByName: (name, face, Fn) => {
        logging.debug("Now try to get user ByName, name: %s", name);

        let sql = "select * from user where name = ? limit 1";
        DataAccess.connection.query(sql, [name], (err, rows, fields) => {
            if (err) {
                let msg = "Mysql query by name error! e: %s" + err;
                logging.error(msg);
                return;
            }
            if (rows && rows.length > 0) {
                let u = rows[0];

                logging.info("User has been obtained, name: %s, id: %s", name, u.id);
                Fn(u.id);
            }else{
                logging.info("Cannot get user, create one. name: %s", name);
                DataAccess.createUser(null, name, face, Fn);
            }
        })
    },
    getUser: (uid, name, face, Fn) => {
        if (DataAccess.connection === undefined){
            setTimeout(() => {DataAccess.getUser(uid, name, face, Fn)}, 500);
            return;
        }

        if (uid){
            DataAccess.getUserByUid(uid, name, face, Fn);
        }else{
            DataAccess.getUserByName(name, face, Fn);
        }
    },
    createGiftRec: (uid, name, face, values) => {
        let saveGift = (sender_id) => {
            logging.debug("Now create GiftRec, sender_id: %s, uid: %s, name: %s", sender_id, uid, name);
            let sql = "" +
                "insert into giftrec" +
                "(`key`, room_id, gift_id, gift_name, gift_type, sender_id, sender_type, created_time, status) " +
                "values(?, ?, ?, ?, ?, ?, ?, ?, ?)";
            DataAccess.connection.query(sql, [
                values.key,
                values.room_id,
                values.gift_id,
                values.gift_name,
                values.gift_type,
                sender_id,
                values.sender_type,
                values.created_time,
                values.status
            ], (err, rows, fields) => {
                if (err) {
                    let msg = "Mysql createGiftRec error! e: " + err;
                    logging.error(msg);
                    return;
                }
                logging.info(
                    "Gift recorded, giftrec id: %s, room_id: %s, gift_type: %s, sender name: %s, uid: %s",
                    rows.insertId, values.gift_id, values.gift_type, name, sender_id
                );
            });
        };
        DataAccess.getUser(uid, name, face, saveGift);
    },
    checkIfGiftExisted: (key, Fn) => {
        if (DataAccess.connection === undefined){
            setTimeout(() => {DataAccess.checkIfGiftExisted(key, Fn)}, 500);
            return;
        }
        let sql = "select * from giftrec where `key` = ? limit 1";
        DataAccess.connection.query(sql, [key], (err, rows, fields) => {
            if (err) {
                let msg = "Mysql query error in checkIfGiftExisted! e: %s" + err;
                logging.error(msg);
                Fn(msg, false);
                return ;
            }
            Fn(undefined, rows && rows.length > 0);
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
    ___getByAdminList_delAdminList: (name, Fn, cookie, csrf_token, anchor_id, uid) => {
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
                logging.error("Add admin error! e: %s", err.toString());
            }
            Fn();
        };
        request(delAdminReqParam, onResponse);
    },
    ___getByAdminList_getAdminList: (name, Fn, cookie, csrf_token, anchor_id) => {
        let reqParam = {
            url: "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/get_by_anchor?page=1",
            method: "get",
            headers: {"User-Agent": UA, "Cookie": cookie},
            timeout: 20000,
        };
        let onResponse = (err, res, body) => {
            if (err) {
                logging.error("read adminList error! e: %s", err.toString());
                UidAcquirer.__ADMIN_WAY_LOCK = null;
                Fn("Cannot read admin list!", null);
                return;
            }
            let r = {"-": "-"};
            try {
                r = JSON.parse(body.toString());
            } catch (e) {
                logging.error(
                    "Error response JSON, in ___getByAdminList_getAdminList. e: %s, body:\n-------\n%s\n\n",
                    e.toString(), body
                );

                UidAcquirer.__ADMIN_WAY_LOCK = null;
                Fn("Error response JSON in ___getByAdminList_getAdminList!", null);
                return;
            }

            let result = (r.data || {}).data || [];
            let uid = null;
            for (let i = 0; i < result.length; i++){
                if (result[i].uname === name){
                    uid = result[i].uid;
                    break;
                }
            }
            if(uid === null) {
                UidAcquirer.__ADMIN_WAY_LOCK = null;
                Fn("Cannot add admin for user: " + name + ", msg: " + r.message, null)
            }else{
                let callback = () => {
                    UidAcquirer.__ADMIN_WAY_LOCK = null;
                    Fn(undefined, uid);
                };
                UidAcquirer.___getByAdminList_delAdminList(name, callback, cookie, csrf_token, anchor_id, uid);
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

        let cca = UidAcquirer.__getCookieCsrfTokenAnchorid();
        let cookie = cca[0] || "";
        let csrf_token = cca[1] || "";
        let anchor_id = cca[2] || 0;
        if(cookie.length < 5 || csrf_token.length < 5 || !anchor_id){
            logging.error("When get uid by admin list find an error cookie!");

            UidAcquirer.__ADMIN_WAY_LOCK = null;
            Fn("Error cookie", null);
            return;
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
            if (err) {
                logging.error("Add admin error! e: %s", err.toString());
            }
            UidAcquirer.___getByAdminList_getAdminList(name, Fn, cookie, csrf_token, anchor_id);
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
                Parser.__getTVGiftIdTask = setInterval(Parser.__getTVGiftId, 2000);
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
            if (r.code !== 0) {return}
            let gidlist = (r.data || {}).list || [];

            let procDist = {};
            for (let i = 0; i < gidlist.length; i++) {
                let gidObject = gidlist[i];

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
            let usernames = Object.keys(procDist);
            for(let i = 0; i < usernames.length; i++){
                let name = usernames[i];
                setTimeout(() => {Parser.__recoredByUser(name, procDist[name])}, 500*(i+1));
            }
        };
        request(reqParam, cbFn);
    },
    __recoredByUser: (name, giftList) => {
        logging.debug("__recoredSingle: %s", JSON.stringify(giftList));

        let callback = (e, uid) => {
            if(e){
                logging.error("Cannot get uid by name: %s, e: %s", name, e);
                uid = null;
            }
            for (let i = 0; i < giftList.length; i++){
                let info = giftList[i];

                let face = info.from_user.face;
                let room_id = info.room_id;
                let gift_id = info.raffleId;
                let gift_creation_valuse = {
                    key: "_T" + room_id + "$" + gift_id,
                    room_id: room_id,
                    gift_id: gift_id,
                    gift_name: info.title,
                    gift_type: info.type,
                    sender_type: info.sender_type,
                    created_time: info.created_time,
                    status: info.status,
                };
                logging.info("create: name: %s, uid: %s, gift_id: %s", name, uid, gift_id);
                DataAccess.createGiftRec(uid, name, face, gift_creation_valuse);
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

            let gidlist = r.data || [];
            for (let i = 0; i < gidlist.length; i++) {
                let giftInfo = gidlist[i];
                giftInfo.created_time = getLocalTimeStr();

                let gift_id = parseInt(giftInfo.id) || 0;
                let k = "NG" + room_id + "$" + gift_id;

                DataAccess.checkIfGiftExisted(k, (e, result) => {
                    if(e){
                        logging.error("Error happened in checkIfGiftExisted: %s", e);
                        return;
                    }
                    if(result){
                        logging.warn("Gift already existed! room_id: %s, gift id: %s", room_id, gift_id);
                    }else{
                        let uid = giftInfo.sender.uid;
                        let name = giftInfo.sender.uname;
                        let face = giftInfo.sender.face;
                        let gift_creation_valuse = {
                            key: k,
                            room_id: room_id,
                            gift_id: gift_id,
                            gift_name: "guard",
                            gift_type: "G" + giftInfo.privilege_type,
                            sender_type: null,
                            created_time: giftInfo.created_time,
                            status: giftInfo.status,
                        };
                        logging.info("create: name: %s, uid: %s, gift_id: %s", name, uid, gift_id);
                        DataAccess.createGiftRec(uid, name, face, gift_creation_valuse);
                    }
                });
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
            }
        })
    },
    init: () => {
        setInterval(GuardListener.getGuardList, 5*60*1000);
        GuardListener.getGuardList();
    },
};


DataAccess.init();
Receiver.init();
GuardListener.init();
