let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
let request = require("request");
let proj_config = require("../config/proj_config");
let env = proj_config.env;

let logging = require("../config/loggers").tvrecorder;
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
                logging.info("Gift recorded, giftrec id: %s", rows.insertId);
            });
        };
        DataAccess.getUser(uid, name, face, saveGift);
    }
};

DataAccess.init();

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

let cb = (e, uid) => {
    if (e){
        console.log("Error in getUidByName: %s", e);
        return;
    }
    console.log("Get uid by name, uid: %s", uid);
};

UidAcquirer.getUidByName("账号已删除1502", cb);
UidAcquirer.getUidByName("ss2", cb);
UidAcquirer.getUidByName("账号已删除", cb);

// DataAccess.createGiftRec(111133335, "亻白亻二丶23", "", {
//         key: "_T999120$11111",
//         room_id: 999120,
//         gift_id: 11111,
//         gift_name: "test",
//         gift_type: "test_type",
//         sender_type: null,
//         created_time: getLocalTimeStr(),
//         status: 0,
//     }
// );
