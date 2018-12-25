let request = require("request");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";


class Acceptor {
    constructor(cookieDictList, loggerDict, defaultLogger) {
        this.cookieDictList = cookieDictList || [];
        this.loggerDict = loggerDict || {};
        this.defaultLogger = defaultLogger;
    }
    acceptGuardSingle(room_id, index) {
        let logging = this.loggerDict[this.cookieDictList[index].csrf_token] || this.defaultLogger;
        let csrf_token = this.cookieDictList[index].csrf_token;
        let cookie = this.cookieDictList[index].cookie;
        let joinFn = (gift_id) => {
            request.post({
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
            }, function (err, res, body) {
                if (err) {
                    logging.error("Error happened (r: " + room_id + "): " + err.toString());
                } else {
                    let r = JSON.parse(body.toString());
                    if (r.code === 0) {
                        let msg = r.data.message;
                        logging.info("Succeed: [" + room_id + " - " + gift_id + "] -> " + msg + " from: " + r.data.from);
                    }
                }
            });
        };
        request({
            url: "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA, "Cookie": cookie},
            timeout: 20000,
        },function (err, res, body) {
            if(err){
                logging.error("Accept single guard error: %s, room_id: %s", err.toString(), room_id);
            }else{
                let r = JSON.parse(body.toString());
                if(r.code === 0){
                    let data = r.data || [];
                    if (data.length === 0){
                        logging.warn("INVALID_GUARD_NOTICE, CANNOT JOIN -> %s", room_id)
                    }else{
                        data.forEach(function(d){joinFn(parseInt(d.id))})
                    }
                }
            }
        })
    };
    acceptGuard(room_id){
        for (let i = 0; i < this.cookieDictList.length; i++){
            this.acceptGuardSingle(room_id, i);
        }
    };
    acceptTvSingle(room_id, index){
        let logging = this.loggerDict[this.cookieDictList[index].csrf_token] || this.defaultLogger;
        let csrf_token = this.cookieDictList[index].csrf_token;
        let cookie = this.cookieDictList[index].cookie;

        let joinFn = (gift_id, title, sender) => {
            request({
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
            }, function (err, res, body) {
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
                        let giftid = data.raffleId,
                            gtype = data.type;
                        logging.info(
                            "TV ACCEPTOR: SUCCEED! room id: %s, gift id: %s, title: %s, sender: %s",
                            room_id, giftid, title, sender
                        );
                    }else{
                        logging.error("TV ACCEPTOR: Failed! r: %s", JSON.stringify(r));
                    }
                }
            });
        };
        let getTvGiftId = (room_id) => {
            request({
                url: "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=" + room_id,
                method: "get",
                headers: {"User-Agent": UA, "Cookie": cookie},
                timeout: 20000,
            },function (err, res, body) {
                if(err){
                    logging.error("Get tv gift id error: %s, room_id: %s", err.toString(), room_id);
                }else{
                    let r = {"-": "-"};
                    try{
                        r = JSON.parse(body.toString());
                    }catch (e) {
                        logging.error("Error response getTvGiftId: %s, body:\n-------\n%s\n\n", e.toString(), body);
                        return;
                    }
                    if(r.code === 0){
                        let data = r.data || {};
                        let gidlist = data.list || [];
                        if(gidlist.length === 0){
                            logging.warn("INVALID_TV_NOTICE, CANNOT JOIN -> %s", room_id);
                        }
                        for (let i = 0; i < gidlist.length; i++){
                            let gid = parseInt(gidlist[i].raffleId) || 0,
                                title = gidlist[i].title || "Unknown",
                                sender = gidlist[i].from;
                            if (gid !== 0){joinFn(gid, title, sender)}
                        }
                    }
                }
            })
        };
        getTvGiftId(room_id);
    }
    acceptTv(room_id){
        let fn = this.acceptTvSingle;
        for (let i = 0; i < 1; /* this.cookieDictList.length;*/ i++){
            setTimeout(function(){fn(room_id, i)}, Math.random()*1000*90);
        }
    }
}
module.exports.Acceptor = Acceptor;


/*
function getStormGift(room_id, gift_id, req_times){
    req_times = req_times || 0;
    let parseResponse = function (err, res, body) {
        if (err) {
            logging.error("Err: ", err);
            getStormGift(room_id, gift_id, req_times + 1);
        } else {
            let r = JSON.parse(body);
            if (r.code !== 0){
                if(req_times < 150){
                    if (req_times > 50 && (req_times%10) === 0){
                        setTimeout(function(){getStormGift(room_id, gift_id, req_times + 1);}, 130)
                    }else{
                        getStormGift(room_id, gift_id, req_times + 1);
                    }
                }else{
                    p_logging.error("Failed! ", room_id);
                }
            }else{
                p_logging.info("Succeed! ", room_id, r.data.mobile_content, ", req_times: ", req_times);
            }
        }
    };
    let reqParam = {
        url: "https://api.live.bilibili.com/lottery/v1/Storm/join",
        headers: headers,
        timeout: 5000,
        form: {
            id: gift_id,
            color: 8322816,
            captcha_token: "",
            captcha_phrase: "",
            roomid: room_id,
            csrf_token: csrf_token,
            csrf: csrf_token,
            visit_id: "",
        }
    };
    request.post(reqParam, parseResponse);
}
function getStormId(room_id){
    let parseStormId = function (err, res, body) {
        if (err) {
            logging.error("Error: ", err);
        } else {
            let r = JSON.parse(body);
            if (r.code === 0 && r.data.hasJoin === 0) {
                logging.info("getStormGift room_id: ", room_id, ", gift_id: ", r.data.id);
                getStormGift(room_id, r.data.id);
            }
        }
    };
    let reqParam = {
        url: "https://api.live.bilibili.com/lottery/v1/Storm/check?roomid=" + room_id,
        method: "get",
        headers: headers,
        timeout: 5000,
    };
    request(reqParam, parseStormId);
}*/

