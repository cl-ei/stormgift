let request = require("request");
let fs = require('fs');
let log4js = require('log4js');
let DEBUG = !(process.argv.splice(2)[0] === "server");

let logerconf = {
  appenders: {
    guard: {
      type: 'file',
      filename: DEBUG ? './log/guard.log' : "/home/wwwroot/log/guard.log",
      maxLogSize: 1024*1024*50,
      backups: 2,
    },
    console: { type: 'console' }
  },
  categories: {
    guard: { appenders: ['guard', 'console'], level: 'ALL' },
    default: { appenders: ['console'], level: 'trace' }
  }
};
log4js.configure(logerconf);
let logging = log4js.getLogger('guard');

let cookie_filename = DEBUG ? './cookie.txt' : "/home/wwwroot/notebook.madliar/notebook_user/i@caoliang.net/cookie.txt";
let cookie = fs.readFileSync(cookie_filename, "utf-8");
let cookie_kv = cookie.split(";");
let csrf_token = "";
for (let i = 0; i < cookie_kv.length; i++){
    let kvstr = cookie_kv[i];
    if (kvstr.indexOf("bili_jct") > -1){
        csrf_token = kvstr.split("=")[1].trim();
        break;
    }
}
let UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36';
let headers = {"User-Agent": UA, "Cookie": cookie};
function guardJoin(giftId, roomId){
    console.log("s -> ", giftId, roomId);

    let reqParam = {
        url: "https://api.live.bilibili.com/lottery/v2/Lottery/join",
        headers: headers,
        timeout: 5000,
        form: {
            roomid: roomId,
            id: giftId,
            type: "guard",
            csrf_token: csrf_token,
            csrf: csrf_token,
            visit_id: "",
        }
    };
    request.post(reqParam, function(err, res, body){
        if(err){
            logging.error("Error happend (r: " + roomId + "): " + err.toString());
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                let msg = r.data.message;
                logging.info("Succeed: [" + roomId + " - " + giftId + "] -> " + msg + " from: " + r.data.from);
            }
        }
    });
}
function getGuardGiftId(roomId, reqTimes){
    reqTimes = reqTimes || 0;
    request({
        url: "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=" + roomId,
        method: "get",
        headers: headers,
        timeout: 10000,
    }, function (err, res, body) {
        if(err){
            logging.error("Error happend (r: " + roomId + ", in get_gift_id): " + err.toString());
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                let data = r.data || [];
                data.forEach(function(d){guardJoin(parseInt(d.id), roomId);})
            }
        }
    });
}
function getGuardList(){
    let parseResponse = function (err, res, body) {
        if (err) {
            logging.error("Get guard info: ", err);
            return ;
        }
        let ptn = /https:\/\/live.bilibili.com\/(\d+)/g;
        let roomUrlList = body.toString().match(ptn);
        roomUrlList.forEach(function(url){getGuardGiftId(url.slice(26))});
    };
    let reqParam = {
        url: "https://dmagent.chinaeast2.cloudapp.chinacloudapi.cn:23333/Governors/View",
        headers: {"User-Agent": UA},
        timeout: 5000,
    };
    request.get(reqParam, parseResponse);
}

getGuardList();
