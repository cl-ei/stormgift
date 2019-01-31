let request = require("request");
let fs = require("fs");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";

let loggers = require("../config/loggers");
let acceptor_logging = loggers.acceptor;
let guard_logging = loggers.apz_guard;
let other_users_logging = loggers.apz_other_users;


let loadCookieFile = () => {
    let COOKIE_FILE_PATH = '/home/wwwroot/stormgift/data/cookie.json';
    return JSON.parse(fs.readFileSync(COOKIE_FILE_PATH,'utf-8'));
};


let Acceptor = {
    __GIFT_ID_POOL: [],
    __getGIDTask: 0,
    __joinDispatcherTask: 0,

    accept: (k) => {
        if (Acceptor.__GIFT_ID_POOL.indexOf(k) < 0) {
            Acceptor.__GIFT_ID_POOL.push(k);
        }
        if (Acceptor.__GIFT_ID_POOL.length > 0 && Acceptor.__joinDispatcherTask === 0){
            Acceptor.__joinDispatcherTask = setInterval(
                () => {Acceptor.__joinDispatcher()},
                500
            );
        }
    },
    __joinDispatcher: () => {
        let k = Acceptor.__GIFT_ID_POOL.shift();
        if(Acceptor.__GIFT_ID_POOL.length === 0 && Acceptor.__joinDispatcherTask !== 0){
            clearInterval(Acceptor.__joinDispatcherTask);
            Acceptor.__joinDispatcherTask = 0;
        }

        let rg = k.split("$");
        let room_id = parseInt(rg[0]),
            gift_id = parseInt(rg[1]);

        let cookieFile = loadCookieFile();
        let cookieList = cookieFile.RAW_COOKIE_LIST;
        let blackList = cookieFile.BLACK_LIST;
        for(let i = 0; i < cookieList.length; i++){
            if(blackList.indexOf(i) > -1){continue}
            let cookie = cookieList[i];
            setTimeout(
                () => {Acceptor.__joinGuardSingle(i, room_id, gift_id, cookie)},
                500*(i + 1)
            );
        }
    },
    __joinGuardSingle: (index, room_id, gift_id, cookie) => {
        let csrf_token = "";
        let cookie_kv = cookie.split(";");
        for (let i = 0; i < cookie_kv.length; i++){
            let kv = cookie_kv[i];
            if (kv.indexOf("bili_jct") > -1){
                csrf_token = kv.split("=")[1].trim();
                break;
            }
        }
        if (csrf_token.length < 10){
            acceptor_logging.error("In guard acceptor, find bad cookie! index: %s, cookie: %s.", index, cookie);
            return;
        }
        let reqParam = {
            url: "https://api.live.bilibili.com/lottery/v2/Lottery/join",
            headers: {"User-Agent": UA, "Cookie": cookie},
            timeout: 20000,
            form: {
                roomid: room_id,
                id: gift_id,
                type: "guard",
                csrf_token: csrf_token,
                csrf: csrf_token,
                visit_id: "",
            }
        },
        cbFn = (err, res, body) => {
            let logging = (index === 0 ? guard_logging : other_users_logging);
            if (err) {
                logging.error("%s - Accept guard prize error: %s, room_id: %s", index, err.toString(), room_id);
            } else {
                let r = {"-": "-"};
                try{
                    r = JSON.parse(body.toString());
                }catch (e) {
                    logging.error(
                        "%s - Error response __joinGuardSingle: %s, body:\n-------\n%s\n\n",
                        index, e.toString(), body
                    );
                    return;
                }
                if(r.code === 0){
                    let data = r.data || {};
                    let msg = data.message,
                        from = data.from;
                    logging.info(
                        "%s - GUARD ACCEPTOR: SUCCEED! room_id: %s, gift_id: %s, msg: %s, from: %s",
                        index, room_id, gift_id, msg, from
                    );
                }else{
                    logging.error("%s - GUARD: __joinGuardSingle Failed! r: %s", index, JSON.stringify(r));
                }
            }
        };
        acceptor_logging.info("GUARD: \tSEND JOIN REQ, index: %s, room_id: %s, gift_id: %s", index, room_id, gift_id);
        request.post(reqParam, cbFn);
    },
};

module.exports.Acceptor = Acceptor;
