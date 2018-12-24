let request = require("request");
let net = require('net');

let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";
let DEBUG = !(process.argv.splice(2)[0] === "server");

let logger = require("./utils/logger");
let logging = logger.creatLogger('guardintervalscanner', DEBUG ? "./log/" : "/home/wwwroot/log/");
logging.info("Start guardintervalscanner proc, ENV: %s", DEBUG ? "DEBUG" : "SERVER");


let PRIZE_NOTICE_HOST = DEBUG ? "111.230.235.254" : "localhost";
let PRIZE_NOTICE_PORT = 11111;
let __prizeSenderList = [];
let sendPrizeMessage = (message) => {
    if(__prizeSenderList.length > 0){
        if (__prizeSenderList[0].write(message) !== true){
            logging.error("Prize message send failed: %s", message);
        }
    }else{
        logging.info("Default prize sender: %s", message);
    }
};
let __generateNoticeSender = () => {
    let __prizeNoticeClient = new net.Socket();
    __prizeNoticeClient.on("error", () => {
        // logging.error("Error happened in prizeNoticeClient.");
        __prizeNoticeClient.destroy();
    });
    __prizeNoticeClient.on('data', (data) => {
        logging.info('Client received: ' + data);
    });
    __prizeNoticeClient.on('close', () => {
        logging.error('Connection closed! Unexpected!');
        while(__prizeSenderList.pop() !== undefined){}
        setTimeout(__generateNoticeSender, 500);
    });
    let onConnected = () => {
        logging.info("PrizeNoticeClient connected.");
        __prizeSenderList.push(__prizeNoticeClient);
    };
    __prizeNoticeClient.connect(PRIZE_NOTICE_PORT, PRIZE_NOTICE_HOST, onConnected);
};
__generateNoticeSender();


let __g_existed_guard = {
    0: [],
    1: [],
    2: [],
};

let filtedExisted = (level, list) => {
    let oldList = __g_existed_guard[level] || [];
    let matchStr = list.join("_"),
        repeatedLength = 0;

    for (let index = 0; index < oldList.length; index++){
        let cmpStr = oldList.slice(index).join("_");
        if (matchStr.indexOf(cmpStr) === 0){
            repeatedLength = cmpStr.length;
            break;
        }
    }
    let avaliableL = matchStr.slice(repeatedLength).split("_"),
        finnalList = [];
    for (let i = 0; i < avaliableL.length; i++){
        let c = avaliableL[i];
        if(c.length > 0){
            finnalList.push(c);
            setTimeout(function(){
                sendPrizeMessage("_G" + c);
            }, Math.random()*1000);
        }
    }
    __g_existed_guard[level] = list;
    logging.info("Get new guard: level: %d, room_id_list: %s", level, finnalList);
};

let getGuardList = () => {
    request({
        url: "https://dmagent.chinanorth.cloudapp.chinacloudapi.cn:23333/Governors/View",
        method: "get",
        headers: {"User-Agent": UA},
        timeout: 10000,
    },function (err, res, body) {
        if(err){
            logging.error("Error happened: %s, r: %s", err.toString(), body.toString())
        }else{
            let response = body.toString();
            if (response.indexOf("提督列表") < 0 || response.indexOf("舰长列表") < 0){
                logging.error("Response data error! r: %s", body.toString());
                return;
            }
            let z_tj = response.split("提督列表");
            let t_j = z_tj[1].split("舰长列表");
            let unFilteredGuardList = [
                z_tj[0].match(/live.bilibili.com\/(\d+)/g),
                t_j[0].match(/live.bilibili.com\/(\d+)/g),
                t_j[1].match(/live.bilibili.com\/(\d+)/g),
            ];
            logging.info("Get guard list success!");
            for (let level = 0; level < unFilteredGuardList.length; level++){
                let uf = unFilteredGuardList[level],
                    current = [];
                for (let i = 0; i < uf.length; i++){current.push(uf[i].match(/\d+/g)[0])}
                filtedExisted(level, current);
            }
        }
    })
};


(() => {
    setInterval(getGuardList, 1000*90);
    getGuardList();
})();
