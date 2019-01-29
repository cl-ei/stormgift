let request = require("request");
let fs = require("fs");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";

let loggers = require("../config/loggers");
let acceptor_logging = loggers.acceptor;
let tv_logging = loggers.apz_tv;
let other_users_logging = loggers.apz_other_users;


let loadCookieList = () => {
    let COOKIE_FILE_PATH = '/home/wwwroot/stormgift/data/cookie.json';
    return JSON.parse(fs.readFileSync(COOKIE_FILE_PATH,'utf-8')).RAW_COOKIE_LIST;
};


let Acceptor = {
    cookieDictList: [],

    __ROOM_ID_POOL: [],
    __GIFT_ID_POOL: [],
    __getTVGiftIdTask: 0,
    __joinTVDispatcherTask: 0,

    __INVALID_PRIZE_POOL: [],
    accept: (room_id) => {
        if (Acceptor.__ROOM_ID_POOL.indexOf(room_id) < 0) {
            Acceptor.__ROOM_ID_POOL.push(room_id);
            if (Acceptor.__getTVGiftIdTask === 0) {
                Acceptor.__getTVGiftIdTask = setInterval(() => {Acceptor.__getTVGiftId()},1000);
            }
        }
    },
    __getTVGiftId: () => {
        let room_id = Acceptor.__ROOM_ID_POOL.shift();
        if(Acceptor.__ROOM_ID_POOL.length === 0 && Acceptor.__getTVGiftIdTask !== 0){
            clearInterval(Acceptor.__getTVGiftIdTask);
            Acceptor.__getTVGiftIdTask = 0;
        }
        let reqParam = {
            url: "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA},
            timeout: 20000,
        },
        cbFn = (err, res, body) => {
            if (err) {
                acceptor_logging.error("Get tv gift id error: %s, room_id: %s", err.toString(), room_id);
                return;
            }
            let r = {"-": "-"};
            try {
                r = JSON.parse(body.toString());
            } catch (e) {
                acceptor_logging.error("Error response getTvGiftId: %s, body:\n-------\n%s\n\n", e.toString(), body);
                return;
            }

            let gidList = (r.data || {}).list || [];
            for (let i = 0; i < gidList.length; i++) {
                let gift_id = parseInt(gidList[i].raffleId) || 0,
                    title = gidList[i].title || "Unknown",
                    from = gidList[i].from;
                let k = [room_id, gift_id, title, from].join("$");

                if (Acceptor.__GIFT_ID_POOL.indexOf(k) < 0 && Acceptor.__checkGiftAvailable(k)){
                    Acceptor.__GIFT_ID_POOL.push(k);
                    if (Acceptor.__joinTVDispatcherTask === 0){
                        Acceptor.__joinTVDispatcherTask = setInterval(() => {Acceptor.__joinTVDispatcher()},400);
                    }
                }
            }
        };
        acceptor_logging.info("\tGET gift list for room_id: %s",room_id);
        request(reqParam, cbFn);
    },
    __joinTVDispatcher: () => {
        let k = Acceptor.__GIFT_ID_POOL.shift();
        if(Acceptor.__GIFT_ID_POOL.length === 0 && Acceptor.__joinTVDispatcherTask !== 0){
            clearInterval(Acceptor.__joinTVDispatcherTask);
            Acceptor.__joinTVDispatcherTask = 0;
        }
        if(!Acceptor.__checkGiftAvailable(k, true)){
            acceptor_logging.warn("INVALID k: %s, SKIP IT!", k);
            return;
        }
        let rg = k.split("$");
        let room_id = parseInt(rg[0]),
            gift_id = parseInt(rg[1]),
            title = rg[2],
            from = rg[3];

        let cookieList = loadCookieList();
        for (let i = 0; i < cookieList.length; i++){
            let cookie = cookieList[i];
            setTimeout(
                () => {Acceptor.__joinTVSingle(i, room_id, gift_id, title, from, cookie)},
                1000*(i + 1)
            )
        }
    },
    __joinTVSingle: (index, room_id, gift_id, title, from, cookie) => {
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
            acceptor_logging.error("In tv acceptor, find bad cookie! index: %s, cookie: %s.", index, cookie);
            return;
        }

        let logging = (index === 0 ? tv_logging : other_users_logging);

        let reqParam = {
            url: "https://api.live.bilibili.com/gift/v3/smalltv/join",
            method: "post",
            headers: {"User-Agent": UA, "Cookie": cookie},
            form: {
                roomid: room_id,
                raffleId: gift_id,
                type: "Gift",
                csrf_token: csrf_token,
                csrf: csrf_token,
                visit_id: "",
            },
            timeout: 20000,
        },
        cbFn = (err, res, body) => {
            if (err) {
                logging.error("%s - Accept tv prize error: %s, room_id: %s", csrf_token, err.toString(), room_id);
            } else {
                let r = {"-": "-"};
                try{
                    r = JSON.parse(body.toString());
                }catch (e) {
                    logging.error(
                        "%s - Error response acceptTvSingle JoinFn: %s, body:\n-------\n%s\n\n",
                        csrf_token, e.toString(), body
                    );
                    return;
                }
                if(r.code === 0){
                    let data = r.data || {};
                    let gift_id = data.raffleId,
                        gtype = data.type;
                    logging.info(
                        "%s - TV ACCEPTOR: SUCCEED! room id: %s, gift id: %s, gtype: %s, from: %s",
                        csrf_token, room_id, gift_id, title, from
                    );
                }else{
                    logging.error("%s - TV ACCEPTOR: Failed! r: %s", csrf_token, JSON.stringify(r));
                }
            }
        };
        acceptor_logging.info("\tSEND JOIN REQ, index: %s, room_id: %s, gift_id: %s", index, room_id, gift_id);
        request(reqParam, cbFn);
    },
    __checkGiftAvailable: (k, autoset) => {
        let r = Acceptor.__INVALID_PRIZE_POOL.indexOf(k) < 0;
        if(r && autoset === true){
            Acceptor.__INVALID_PRIZE_POOL.push(k);
            while(Acceptor.__INVALID_PRIZE_POOL.length > 2000){
                Acceptor.__INVALID_PRIZE_POOL.shift();
            }
        }
        return r;
    },
};

module.exports.Acceptor = Acceptor;
