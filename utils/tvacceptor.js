let request = require("request");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";

let loggers = require("../config/loggers");
let acceptor_logging = loggers.acceptor;
let tv_logging = loggers.apz_tv;
let other_users_logging = loggers.apz_other_users;

let Acceptor = {
    cookieDictList: [],

    __ROOM_ID_POOL: [],
    __GIFT_ID_POOL: [],
    __getTVGiftIdTask: 0,
    __joinTVDispatcherTask: 0,

    __INVALID_PRIZE_POOL: [],
    init: (cookieDict) => {
        Acceptor.cookieDictList = cookieDict;
    },
    accept: (room_id) => {
        if (Acceptor.__ROOM_ID_POOL.indexOf(room_id) < 0) {
            Acceptor.__ROOM_ID_POOL.push(room_id);
            if (Acceptor.__getTVGiftIdTask === 0) {
                Acceptor.__getTVGiftIdTask = setInterval(Acceptor.__getTVGiftId, 1000);
                acceptor_logging.info("Start __getTVGiftId task, task id: %s.", Acceptor.__getTVGiftIdTask);
            }
        }
    },
    __getTVGiftId: () => {
        let room_id = Acceptor.__ROOM_ID_POOL.shift();
        acceptor_logging.info("getTVGiftId search room: %s", room_id);
        if(Acceptor.__ROOM_ID_POOL.length === 0 && Acceptor.__getTVGiftIdTask !== 0){
            clearInterval(Acceptor.__getTVGiftIdTask);
            Acceptor.__getTVGiftIdTask = 0;
            acceptor_logging.info("Kill __getTVGiftId task. Last proc room_id: %s.", room_id);
        }

        let default_cookie = Acceptor.cookieDictList[0].cookie;
        let reqParam = {
            url: "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA, "Cookie": default_cookie},
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
            if (r.code !== 0) {return}

            let data = r.data || {};
            let gidlist = data.list || [];
            if (gidlist.length === 0) {acceptor_logging.warn("INVALID_TV_NOTICE, CANNOT JOIN -> %s", room_id)}

            for (let i = 0; i < gidlist.length; i++) {
                let gift_id = parseInt(gidlist[i].raffleId) || 0,
                    title = gidlist[i].title || "Unknown",
                    from = gidlist[i].from;

                let k = [room_id, gift_id, title, from].join("$");
                if (Acceptor.__GIFT_ID_POOL.indexOf(k) < 0 && Acceptor.__checkGiftAvailable(k)){
                    Acceptor.__GIFT_ID_POOL.push(k);
                    if (Acceptor.__joinTVDispatcherTask === 0){
                        Acceptor.__joinTVDispatcherTask = setInterval(Acceptor.__joinTVDispatcher, 200);
                        acceptor_logging.info(
                            "Start __joinTVDispatcher task, task id: %s.", Acceptor.__joinTVDispatcherTask
                        );
                    }
                }
            }
        };
        acceptor_logging.info("\tSEND GET TVGIFTID REQ, room_id: %s", room_id);
        request(reqParam, cbFn);
    },
    __joinTVDispatcher: () => {
        let k = Acceptor.__GIFT_ID_POOL.shift();
        acceptor_logging.info("Dispatch: %s", k);
        if(Acceptor.__GIFT_ID_POOL.length === 0 && Acceptor.__joinTVDispatcherTask !== 0){
            clearInterval(Acceptor.__joinTVDispatcherTask);
            Acceptor.__joinTVDispatcherTask = 0;
            acceptor_logging.info("Kill __joinTVDispatcher task, Last proc k: %s.", k);
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
        Acceptor.__joinTVSingle(0, room_id, gift_id, title, from);

        let datetime = new Date();
        let hours = datetime.getHours();
        let limitFreq = (hours >= 20 || hours < 1);
        for(let i = 1; i < Acceptor.cookieDictList.length; i++){
            if((limitFreq && Math.random() < 0.9) || (!limitFreq)){
                setTimeout(
                    () => {Acceptor.__joinTVSingle(i, room_id, gift_id, title, from)},
                    Math.random()*1000*70
                );
            }
        }
    },
    __joinTVSingle: (index, room_id, gift_id, title, from) => {
        let csrf_token = Acceptor.cookieDictList[index].csrf_token,
            cookie = Acceptor.cookieDictList[index].cookie;
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
