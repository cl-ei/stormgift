let request = require("request");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";


let Acceptor = {
    cookieDictList: [],
    loggerDict: {},
    defaultLogger: undefined,

    __ROOM_ID_POOL: [],
    __GIFT_ID_POOL: [],
    __getGIDTask: 0,
    __joinDispatcherTask: 0,
    __INVALID_PRIZE_POOL: [],

    init: (cookieDict, loggerDict, defaultLogger) => {
        Acceptor.cookieDictList = cookieDict;
        Acceptor.loggerDict = loggerDict;
        Acceptor.defaultLogger = defaultLogger;
    },
    accept: (room_id) => {
        if (Acceptor.__ROOM_ID_POOL.indexOf(room_id) < 0) {
            Acceptor.__ROOM_ID_POOL.push(room_id);
            if (Acceptor.__getGIDTask === 0) {
                Acceptor.__getGIDTask = setInterval(Acceptor.__getGID, 500);
                Acceptor.defaultLogger.info("GUARD: Start __getGID task.");
            }
        }
    },
    __getGID: () => {
        let room_id = Acceptor.__ROOM_ID_POOL.shift();
        Acceptor.defaultLogger.info("GUARD: __getGID search room: %s", room_id);
        if(Acceptor.__ROOM_ID_POOL.length === 0 && Acceptor.__getGIDTask !== 0){
            clearInterval(Acceptor.__getGIDTask);
            Acceptor.__getGIDTask = 0;
            Acceptor.defaultLogger.info("GUARD: Kill __getGID task. Last proc room_id: %s.", room_id);
        }

        let csrf_token = Acceptor.cookieDictList[0].csrf_token,
            cookie = Acceptor.cookieDictList[0].cookie;
        let logging = Acceptor.loggerDict[csrf_token] || Acceptor.defaultLogger;

        let reqParam = {
            url: "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA, "Cookie": cookie},
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
            if (gidlist.length === 0){return}

            for (let i = 0; i < gidlist.length; i++) {
                let gift_id = parseInt(gidlist[i].id) || 0;
                let k = "" + room_id + "$" + gift_id;

                if (Acceptor.__GIFT_ID_POOL.indexOf(k) < 0 && Acceptor.__checkGiftAvailable(k)){
                    Acceptor.__GIFT_ID_POOL.push(k);
                    if (Acceptor.__joinDispatcherTask === 0){
                        Acceptor.__joinDispatcherTask = setInterval(Acceptor.__joinDispatcher, 200);
                        Acceptor.defaultLogger.info("GUARD: Start __joinDispatcher task.");
                    }
                }
            }
        };
        Acceptor.defaultLogger.info("GUARD:\tSEND GET GUARD GIFT ID REQ, room_id: %s", room_id);
        request(reqParam, cbFn);
    },
    __joinDispatcher: () => {
        let k = Acceptor.__GIFT_ID_POOL.shift();
        Acceptor.defaultLogger.info("GUARD: Dispatch: %s", k);

        if(Acceptor.__GIFT_ID_POOL.length === 0 && Acceptor.__joinDispatcherTask !== 0){
            clearInterval(Acceptor.__joinDispatcherTask);
            Acceptor.__joinDispatcherTask = 0;
            Acceptor.defaultLogger.info("GUARD: Kill __joinDispatcher task, Last proc k: %s.", k);
        }
        if(!Acceptor.__checkGiftAvailable(k, true)){
            Acceptor.defaultLogger.warn("GUARD: INVALID k: %s, SKIP IT!", k);
            return;
        }
        let rg = k.split("$");
        let room_id = parseInt(rg[0]),
            gift_id = parseInt(rg[1]);

        for(let i = 0; i < Acceptor.cookieDictList.length; i++){
            setTimeout(
                () => {Acceptor.__joinGuardSingle(i, room_id, gift_id)},
                300*(i + 1)
            );
        }
    },
    __joinGuardSingle: (index, room_id, gift_id) => {
        let csrf_token = Acceptor.cookieDictList[index].csrf_token,
            cookie = Acceptor.cookieDictList[index].cookie;
        let logging = Acceptor.loggerDict[csrf_token] || Acceptor.defaultLogger;

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
            if (err) {
                logging.error("Accept guard prize error: %s, room_id: %s", err.toString(), room_id);
            } else {
                let r = {"-": "-"};
                try{
                    r = JSON.parse(body.toString());
                }catch (e) {
                    logging.error(
                        "Error response __joinGuardSingle: %s, body:\n-------\n%s\n\n",
                        e.toString(), body
                    );
                    return;
                }
                if(r.code === 0){
                    let data = r.data || {};
                    let msg = data.message,
                        from = data.from;
                    logging.info(
                        "GUARD ACCEPTOR: SUCCEED! room_id: %s, gift_id: %s, msg: %s, from: %s",
                        room_id, gift_id, msg, from
                    );
                }else{
                    logging.error("GUARD: __joinGuardSingle Failed! r: %s", JSON.stringify(r));
                }
            }
        };
        Acceptor.defaultLogger.info("GUARD: \tSEND JOIN REQ, index: %s, room_id: %s, gift_id: %s", index, room_id, gift_id);
        request.post(reqParam, cbFn);
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
