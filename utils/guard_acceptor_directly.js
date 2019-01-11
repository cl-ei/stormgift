let request = require("request");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";

let loggers = require("../config/loggers");
let acceptor_logging = loggers.acceptor;
let guard_logging = loggers.apz_guard;
let other_users_logging = loggers.apz_other_users;

let Acceptor = {
    cookieDictList: [],

    __GIFT_ID_POOL: [],
    __getGIDTask: 0,
    __joinDispatcherTask: 0,

    init: (cookieDict) => {
        Acceptor.cookieDictList = cookieDict;
    },
    accept: (k) => {
        if (Acceptor.__GIFT_ID_POOL.indexOf(k) < 0) {
            Acceptor.__GIFT_ID_POOL.push(k);
        }
        if (Acceptor.__GIFT_ID_POOL.length > 0 && Acceptor.__joinDispatcherTask === 0){
            Acceptor.__joinDispatcherTask = setInterval(Acceptor.__joinDispatcher, 200);
            acceptor_logging.info("GUARD: Start __joinDispatcher task.");
        }
    },
    __joinDispatcher: () => {
        let k = Acceptor.__GIFT_ID_POOL.shift();
        acceptor_logging.info("GUARD: Dispatch: %s", k);

        if(Acceptor.__GIFT_ID_POOL.length === 0 && Acceptor.__joinDispatcherTask !== 0){
            clearInterval(Acceptor.__joinDispatcherTask);
            Acceptor.__joinDispatcherTask = 0;
            acceptor_logging.info("GUARD: Kill __joinDispatcher task, Last proc k: %s.", k);
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
                logging.error("%s - Accept guard prize error: %s, room_id: %s", csrf_token, err.toString(), room_id);
            } else {
                let r = {"-": "-"};
                try{
                    r = JSON.parse(body.toString());
                }catch (e) {
                    logging.error(
                        "%s - Error response __joinGuardSingle: %s, body:\n-------\n%s\n\n",
                        csrf_token, e.toString(), body
                    );
                    return;
                }
                if(r.code === 0){
                    let data = r.data || {};
                    let msg = data.message,
                        from = data.from;
                    logging.info(
                        "%s - GUARD ACCEPTOR: SUCCEED! room_id: %s, gift_id: %s, msg: %s, from: %s",
                        csrf_token, room_id, gift_id, msg, from
                    );
                }else{
                    logging.error("%s - GUARD: __joinGuardSingle Failed! r: %s", csrf_token, JSON.stringify(r));
                }
            }
        };
        acceptor_logging.info("GUARD: \tSEND JOIN REQ, index: %s, room_id: %s, gift_id: %s", index, room_id, gift_id);
        request.post(reqParam, cbFn);
    },
};

module.exports.Acceptor = Acceptor;
