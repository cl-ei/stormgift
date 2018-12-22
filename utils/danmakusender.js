let request = require("request");
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";

class Sender {
    constructor(index, defaultLogger) {
        index = index || 0;
        this.logging = defaultLogger;
        let cookie_filename = '../data/cookie.js';
        let RAW_COOKIES_LIST = require(cookie_filename).RAW_COOKIE_LIST;
        this.cookie = RAW_COOKIES_LIST[index];
        this.csrf_token = "";
        let cookie_kv = this.cookie.split(";");

        for (let i = 0; i < cookie_kv.length; i++){
            let kvstr = cookie_kv[i];
            if (kvstr.indexOf("bili_jct") > -1){
                this.csrf_token = kvstr.split("=")[1].trim();
                break;
            }
        }
        if (this.csrf_token.length < 10){
            throw "Bad csrf token! " + this.csrf_token;
        }
    }
    sendDamaku(message, room_id, color) {
        color = color || 0xffffff;
        let logging = this.logging;
        request.post({
            url: "https://live.bilibili.com/msg/send",
            headers: {"User-Agent": UA, "Cookie": this.cookie},
            timeout: 10000,
            form: {
                "color": color,
                "fontsize": 25,
                "mode": 1,
                "msg": message,
                "rnd": parseInt((new Date()).valueOf().toString().slice(0, 10)),
                "roomid": room_id,
                "csrf_token": this.csrf_token,
            }
        }, function (err, res, body) {
            if (err) {
                logging.error("Error happened to send danmaku, e: ", err.toString());
            }else{
                let response = JSON.parse(body.toString());
                if(response.code === 0){

                }else{
                    logging.error("Error send message: %s -> %s, response: %s", message, room_id, JSON.stringify(response));
                }
            }
        });
    }
}

module.exports.Sender = Sender;
