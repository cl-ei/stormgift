let request = require("request");
let DEBUG = !(process.argv.splice(2)[0] === "server");
let logger = require("../utils/logger");


let cookie_filename = DEBUG ? '../data/cookie.js' : "/home/wwwroot/notebook.madliar/notebook_user/i@caoliang.net/cookie.js";
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
let RAW_COOKIES_LIST = require(cookie_filename).RAW_COOKIE_LIST,
    COOKIE_DICT_LIST = [],
    logerDict = {};

for (let i = 0; i < RAW_COOKIES_LIST.length; i++){
    let cookie = RAW_COOKIES_LIST[i];
    let cookie_kv = cookie.split(";");
    let csrf_token = "";
    for (let i = 0; i < cookie_kv.length; i++){
        let kvstr = cookie_kv[i];
        if (kvstr.indexOf("bili_jct") > -1){
            csrf_token = kvstr.split("=")[1].trim();
            COOKIE_DICT_LIST.push({
               cookie: cookie,
               csrf_token: csrf_token,
            });
            logerDict[csrf_token] = logger.creatLogger(
                'apz_' + csrf_token.slice(csrf_token.length/2),
                DEBUG ? "./log/" : "/home/wwwroot/log/"
            );
            break;
        }
    }
}


let __guardJoin = (room_id, gift_id, cookiedic) => {
    let reqParam = {
        url: "https://api.live.bilibili.com/lottery/v2/Lottery/join",
        headers: {"User-Agent": UA, "Cookie": cookiedic.cookie},
        timeout: 5000,
        form: {
            roomid: room_id,
            id: gift_id,
            type: "guard",
            csrf_token: cookiedic.csrf_token,
            csrf: cookiedic.csrf_token,
            visit_id: "",
        }
    };
    request.post(reqParam, function(err, res, body){
        let logging = logerDict[cookiedic.csrf_token];
        if (logging === undefined){return}
        if(err){
            logging.error("Error happened (r: " + room_id + "): " + err.toString());
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                let msg = r.data.message;
                logging.info("Succeed: [" + room_id + " - " + gift_id + "] -> " + msg + " from: " + r.data.from);
            }
        }
    });
};
let __getGuardGiftId = (room_id, cookiedic) => {
    request({
        url: "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=" + room_id,
        method: "get",
        headers: {"User-Agent": UA, "Cookie": cookiedic.cookie},
        timeout: 10000,
    },function (err, res, body) {
        if(err){
            // TODO: add log.
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                let data = r.data || [];
                data.forEach(function(d){
                    __guardJoin(room_id, parseInt(d.id), cookiedic);
                })
            }
        }
    })
};


let acceptGuardSingle = (room_id, cookiedic) => {
    __getGuardGiftId(room_id, cookiedic);
};

let acceptTvSingle = (room_id, cookie) => {

};


exports.acceptGuard = (room_id) => {
    for (let i = 0; i < COOKIE_DICT_LIST.length; i++){
        acceptGuardSingle(room_id, COOKIE_DICT_LIST[i]);
    }
};
exports.acceptTv = (room_id) => {
    for (let i = 0; i < COOKIE_DICT_LIST.length; i++){
        acceptTvSingle(room_id, COOKIE_DICT_LIST[i]);
    }
};



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

