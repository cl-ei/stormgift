let request = require("request");
let logging = require("../config/loggers").heartbeat;
let UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36';
let RAW_COOKIES_LIST = require('../data/cookie.js').RAW_COOKIE_LIST;


function heartbeat_90s(cookie){
    let reqParam = {
        url: "https://api.live.bilibili.com/relation/v1/Feed/heartBeat",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 5000,
    };
    request.get(reqParam, function (err, res, body) {
        if (err) {
            logging.error("90s Heartbeat send error! ", err.toString());
        }else{
            logging.info("Heartbeat 90s: " + body.toString());
        }
    });
}
function postLatestTime(cookie, index){
    let timest = (new Date()).valueOf();
    request.get({
        url: "https://api.live.bilibili.com/relation/v1/feed/heartBeat?_=" + timest,
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 5000,
    }, function (err, res, body) {
        if (err) {
            logging.error("90s Heartbeat send error, index: %d, e: %s", index, err.toString());
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                logging.info("postLatestTime Success! index: %d, timest: %s", index, timest);
            }else{
                logging.error("postLatestTime Error! index: %d, r: %s", index, body.toString());
            }
        }
    });
}
function heartbeat_5m(cookie, index){
    request.post({
        url: "https://api.live.bilibili.com/User/userOnlineHeart",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 5000,
    }, function (err, res, body) {
        if (err) {
            logging.error(
                "5m Heartbeat send error! index: %s, e: %s, body: %s",
                index, err.toString(), res
            );
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                logging.info("Send Heartbeat Success! index: %d", index);
            }else{
                logging.error("Error happened in 5m, index: %d, r: %s", index, body.toString());
            }
        }
        postLatestTime(cookie, index);
    });
}

(() => {
    logging.info("Start send heartbeat proc.");
    for (let i = 0; i < RAW_COOKIES_LIST.length; i++){
        let c = RAW_COOKIES_LIST[i];
        heartbeat_5m(c, i);
    }
    setTimeout(() => {
        logging.info("Finished. \n\n")
    }, 20000)
})();
