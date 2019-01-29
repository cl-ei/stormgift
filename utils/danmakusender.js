let request = require("request");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";

module.exports.sendDanmaku = (message, room_id, color, cookieIdx, logging) => {
    cookieIdx = cookieIdx || 0;
    let cookie = JSON.parse(fs.readFileSync('../data/cookie.json','utf-8')).RAW_COOKIE_LIST[cookieIdx];
    let csrf_token = "";
    let cookie_kv = cookie.split(";");

    for (let i = 0; i < cookie_kv.length; i++){
        let kvstr = cookie_kv[i];
        if (kvstr.indexOf("bili_jct") > -1){
            csrf_token = kvstr.split("=")[1].trim();
            break;
        }
    }
    if (csrf_token.length < 10){
        if(logging){
            logging.error("Bad csrf token! " + csrf_token)
        }
        return;
    }
    color = color || 0xffffff;
    request.post({
        url: "https://live.bilibili.com/msg/send",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 10000,
        form: {
            "color": color,
            "fontsize": 25,
            "mode": 1,
            "msg": message,
            "rnd": parseInt((new Date()).valueOf()/1000),
            "roomid": room_id,
            "csrf_token": csrf_token,
        }
    }, function (err, res, body) {
        if(logging){
            if (err) {
                logging.error("Error happened to send danmaku, e: ", err.toString());
                return;
            }
            let response = JSON.parse(body.toString());
            if(response.code !== 0){
                logging.error("Error send message: %s -> %s, response: %s", message, room_id, JSON.stringify(response));
            }
        }
    });
};
