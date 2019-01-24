let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
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


DataAccess.createGiftRec(111133335, "亻白亻二丶23", "", {
        key: "_T999120$11111",
        room_id: 999120,
        gift_id: 11111,
        gift_name: "test",
        gift_type: "test_type",
        sender_type: null,
        created_time: getLocalTimeStr(),
        status: 0,
    }
);
