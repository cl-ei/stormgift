let net = require('net');
let logger = require("./utils/logger");
let path = require('path');
let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let loggerFilePath = DEBUG ? "./log" : "/home/wwwroot/log",
    loggerConfigList = [{
        loggerName: "prizehandler",
        loggerFile: path.join(loggerFilePath, "prizehandler.log"),
    }];


let cookie_filename = './data/cookie.js';
let RAW_COOKIES_LIST = require(cookie_filename).RAW_COOKIE_LIST,
    COOKIE_DICT_LIST = [];

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
            loggerConfigList.push({
                loggerName: csrf_token,
                loggerFile: path.join(loggerFilePath, "apz_" + csrf_token.slice(csrf_token.length/2) + ".log"),
            });
            break;
        }
    }
}

let loggers = logger.batchCreateLogger(loggerConfigList);
let logging = loggers["prizehandler"];
logging.info("Start proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));

let damakusender = require("./utils/danmakusender");
let dmksender = new damakusender.Sender(logging);
let DDSLIVE_ROOM_NUMBER = 13369254;
let guardCallBackFn = (room_id, gid, sender) => {
    // let message = "#@" + sender + "在" + room_id + "直播间登船~";
    let message = "G-" + Buffer.from(room_id).toString('base64');
    setTimeout(
        function(){dmksender.sendDamaku(message, DDSLIVE_ROOM_NUMBER)},
        parseInt(Math.random()*1000*2)
    );
};
let tvCallBackFn = (room_id, gid, sender) => {
    // let message = "#^" + sender + "在" + room_id + "发放低保~";
    let message = "T-" + Buffer.from(room_id).toString('base64');
    setTimeout(
        function(){dmksender.sendDamaku(message, DDSLIVE_ROOM_NUMBER)},
        parseInt(Math.random()*1000*2)
    );
};

let Acceptor = require("./utils/acceptprize").Acceptor;
let ac = new Acceptor(COOKIE_DICT_LIST, loggers, logging, guardCallBackFn, tvCallBackFn);

let onMessageReceived = (msg, addr) => {
    if (msg.length < 5 || msg[0] !== "_"){return}
    let giftType = msg[1],
        room_id = parseInt(msg.slice(2));

    if(giftType === "S"){
        logging.info("Gift: %s, room_id: %s", giftType, room_id);
    }else if(giftType === "G"){
        logging.info("Gift: %s, room_id: %s", giftType, room_id);
        ac.acceptGuard(room_id);
    }else if(giftType === "T"){
        logging.info("Gift: %s, room_id: %s", giftType, room_id);
        ac.acceptTv(room_id);
    }
};


(() => {
    let connectionListener = (sock) => {
        logging.info('New client connected: addr: %s, port: %s', sock.remoteAddress, sock.remotePort);
        sock.on('data', function(data) {
            try{onMessageReceived(String(data), sock.remoteAddress)}catch(e){
                logging.error("Proc prize message coursed an error: %s", e.toString())
            }
        });
        sock.on('close', function(data) {
            logging.error('Client closed: addr: %s, port: %s, data: %s', sock.remoteAddress, sock.remotePort, data);
        });
    };
    net.createServer(connectionListener).listen(11111, "0.0.0.0");
})();
