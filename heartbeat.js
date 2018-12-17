let request = require("request");
let fs = require('fs');
let log4js = require('log4js');
let DEBUG = !(process.argv.splice(2)[0] === "server");

let logerconf = {
  appenders: {
    heartbeat: {
      type: 'file',
      filename: DEBUG ? './log/heartbeat.log' : "/home/wwwroot/log/heartbeat.log",
      maxLogSize: 1024*1024*50,
      backups: 2,
    },
    console: { type: 'console' }
  },
  categories: {
    heartbeat: { appenders: ['heartbeat', 'console'], level: 'ALL' },
    default: { appenders: ['console'], level: 'trace' }
  }
};
log4js.configure(logerconf);
let logging = log4js.getLogger('heartbeat');

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

function heartbeat_90s(){
    let reqParam = {
        url: "https://api.live.bilibili.com/relation/v1/Feed/heartBeat",
        headers: headers,
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
function postLatestTime(){
    let timest = (new Date()).valueOf();
    request.get({
        url: "https://api.live.bilibili.com/relation/v1/feed/heartBeat?_=" + timest,
        headers: headers,
        timeout: 5000,
    }, function (err, res, body) {
        if (err) {
            logging.error("90s Heartbeat send error! ", err.toString());
        }else{
            logging.info("Heartbeat (" + timest + ")POST: " + body.toString());
        }
    });
}
function heartbeat_5m(){
    request.post({
        url: "https://api.live.bilibili.com/User/userOnlineHeart",
        headers: headers,
        timeout: 5000,
    }, function (err, res, body) {
        if (err) {
            logging.error("5m Heartbeat send error! ", err.toString());
        }else{
            logging.info("Heartbeat 5m: " + body.toString());
        }
        postLatestTime();
    });
}

heartbeat_5m();

// setInterval(heartbeat_90s, 1000*90);
// setInterval(heartbeat_10m, 1000*60*10);
// setInterval(heartbeat_20m, 1000*60*2);
