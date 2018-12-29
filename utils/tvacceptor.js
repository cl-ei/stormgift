let request = require("request");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";


let Acceptor = {
    cookieDictList: [],
    loggerDict: {},
    defaultLogger: undefined,

    __ROOM_ID_POOL: [],
    __GIFT_ID_POOL: [],
    __getTVGiftIdTask: 0,
    __joinTVTask: 0,

    __INVALID_PRIZE_POOL: [],
    init: (cookieDict, loggerDict, defaultLogger) => {
        Acceptor.cookieDictList = cookieDict;
        Acceptor.loggerDict = loggerDict;
        Acceptor.defaultLogger = defaultLogger;
    },
    accept: (room_id) => {
        if (Acceptor.__ROOM_ID_POOL.indexOf(room_id) < 0) {
            Acceptor.__ROOM_ID_POOL.push(room_id);
            if (Acceptor.__getTVGiftIdTask === 0) {
                Acceptor.__getTVGiftIdTask = setInterval(Acceptor.__getTVGiftId, 2 * 1000);
                Acceptor.defaultLogger.info("Start __getTVGiftId task, task id: %s.", Acceptor.__getTVGiftIdTask);
            }
        }
    },
    __getTVGiftId: () => {
        let room_id = Acceptor.__ROOM_ID_POOL.shift();
        if(Acceptor.__ROOM_ID_POOL.length === 0 && Acceptor.getTVGiftIdTask !== 0){
            clearInterval(Acceptor.getTVGiftIdTask);
            Acceptor.getTVGiftIdTask = 0;
            Acceptor.defaultLogger.info("Kill __getTVGiftId task. Last proc room_id: %s.", room_id);
        }

        let default_csrf_token = Acceptor.cookieDictList[0].csrf_token,
            default_cookie = Acceptor.cookieDictList[0].cookie;
        let logging = Acceptor.loggerDict[default_csrf_token] || Acceptor.defaultLogger;

        request({
            url: "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA, "Cookie": default_cookie},
            timeout: 20000,
        },function (err, res, body) {
            if (err) {
                logging.error("Get tv gift id error: %s, room_id: %s", err.toString(), room_id);
            } else {
                let r = {"-": "-"};
                try {
                    r = JSON.parse(body.toString());
                } catch (e) {
                    logging.error("Error response getTvGiftId: %s, body:\n-------\n%s\n\n", e.toString(), body);
                    return;
                }
                if (r.code !== 0) {return}

                let data = r.data || {};
                let gidlist = data.list || [];
                if (gidlist.length === 0) {logging.warn("INVALID_TV_NOTICE, CANNOT JOIN -> %s", room_id)}

                for (let i = 0; i < gidlist.length; i++) {
                    let gift_id = parseInt(gidlist[i].raffleId) || 0,
                        title = gidlist[i].title || "Unknown",
                        from = gidlist[i].from;

                    let k = "" + room_id + "_" + gift_id;
                    if (Acceptor.__GIFT_ID_POOL.indexOf(k) < 0){
                        Acceptor.__GIFT_ID_POOL.push(k);
                        if (Acceptor.__joinTVTask === 0){
                            Acceptor.__joinTVTask = setInterval(Acceptor.__joinTVDispatcher, 500);
                            Acceptor.defaultLogger.info(
                                "Start __joinTVDispatcher task, task id: %s.", Acceptor.__joinTVTask
                            );
                        }
                    }
                }
            }
        })
    },
    __joinTVDispatcher: () => {
        let k = Acceptor.__GIFT_ID_POOL.shift();
        if(Acceptor.__GIFT_ID_POOL.length === 0 && Acceptor.__joinTVTask !== 0){
            clearInterval(Acceptor.__joinTVTask);
            Acceptor.__joinTVTask = 0;
            Acceptor.defaultLogger.info("Kill __joinTVDispatcher task, Last proc k: %s.", k);
        }
        if(!Acceptor.__checkGiftAvailable(k)){
            Acceptor.defaultLogger.warn("INVALID k: %s, SKIP IT!", k);
            return;
        }
        let rg = k.split("_");
        let room_id = parseInt(rg[0]),
            gift_id = parseInt(rg[1]);
        Acceptor.__joinTVSingle(0, room_id, gift_id);

        let datetime = new Date();
        let hours = datetime.getHours();
        let limitFreq = (hours >= 20 || hours < 1);
        for(let i = 1; i < Acceptor.cookieDictList.length; i++){
            if((limitFreq && Math.random() < 0.3) || (!limitFreq)){
                setTimeout(
                    () => {Acceptor.__joinTVSingle(i, room_id, gift_id)},
                    Math.random()*1000*20
                );
            }
        }
    },
    __joinTVSingle: (index, room_id, gift_id) => {
        let csrf_token = Acceptor.cookieDictList[index].csrf_token,
            cookie = Acceptor.cookieDictList[index].cookie;
        let logging = Acceptor.loggerDict[csrf_token] || Acceptor.defaultLogger;

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
                logging.error("Accept tv prize error: %s, room_id: %s", err.toString(), room_id);
            } else {
                let r = {"-": "-"};
                try{
                    r = JSON.parse(body.toString());
                }catch (e) {
                    logging.error(
                        "Error response acceptTvSingle JoinFn: %s, body:\n-------\n%s\n\n",
                        e.toString(), body
                    );
                    return;
                }
                if(r.code === 0){
                    let data = r.data || {};
                    let gift_id = data.raffleId,
                        gtype = data.type;
                    logging.info(
                        "TV ACCEPTOR: SUCCEED! room id: %s, gift id: %s, gtype: %s, from: %s",
                        room_id, gift_id, gtype, "from-" // title, from
                    );
                }else{
                    logging.error("TV ACCEPTOR: Failed! r: %s", JSON.stringify(r));
                }
            }
        };
        request(reqParam, cbFn);
    },
    __checkGiftAvailable: (k) => {
        let r = Acceptor.__INVALID_PRIZE_POOL.indexOf(k) < 0;
        if(r){
            Acceptor.__INVALID_PRIZE_POOL.push(k);
            while(Acceptor.__INVALID_PRIZE_POOL.length > 2000){
                Acceptor.__INVALID_PRIZE_POOL.shift();
            }
        }
        return r;
    },
};

module.exports.Acceptor = Acceptor;
