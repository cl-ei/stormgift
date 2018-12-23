let request = require("request");
let logger = require("./utils/logger");
let DEBUG = !(process.argv.splice(2)[0] === "server");


let logging = logger.creatLogger('heartbeat', DEBUG ? "./log/" : "/home/wwwroot/log/");
let UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36';
let RAW_COOKIES_LIST = require('./data/cookie.js').RAW_COOKIE_LIST;


function doSign(cookie, index){
    request.get({
        url: "https://api.live.bilibili.com/sign/doSign",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 5000,
    }, function (err, res, body) {
        if (err) {
            logging.error("Do sign error, index: %d, e: %s", index, err.toString());
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                logging.info("doSign Success! index: %d, ", index);
            }else{
                logging.info("doSign Error! index: %d, r: %s", index, body.toString());
            }
        }
    });
}
(() => {
    logging.info("Start doSign proc, ENV: %s", DEBUG ? "DEBUG": "SERVER");
    for (let i = 1; i < RAW_COOKIES_LIST.length; i++){
        let c = RAW_COOKIES_LIST[i];
        doSign(c, i);
    }
})();
