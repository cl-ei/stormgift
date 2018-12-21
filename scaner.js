let request = require("request");
let fs = require("fs");
let log4js = require('log4js');
let DEBUG = !(process.argv.splice(2)[0] === "server");
let ROOM_COUNT_LIMIT = 500;

function creatLogger(loggerName, path_){
  let path = require("path");
  let config = {
    appenders: {console: { type: 'console' }},
    categories: {default: { appenders: ['console'], level: 'trace' }}
  };
  config.appenders[loggerName] = {
        type: 'file',
        filename: path.join(path_, loggerName+ ".log"),
        maxLogSize: 1024*1024*50,
        backups: 2,
  };
  config.categories[loggerName] = {appenders: [loggerName, 'console'], level: 'ALL' };
  log4js.configure(config);
  return log4js.getLogger(loggerName);
}

let logging = creatLogger('scaner', DEBUG ? "./log/" : "/home/wwwroot/log/");
logging.info("Start proc -> DEBUG env: " + DEBUG + ", Room count limit: " + ROOM_COUNT_LIMIT);

let MONITOR_ROOM_LIST = new Set(),
    scan_url = "https://api.live.bilibili.com/room/v1/Area/getListByAreaID?areaId=0&sort=online&pageSize=2000&page=",
    UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36';
let headers = {'User-Agent': UA};
let EMPTY_PAGES_COUNT = 0;

function roomScaner(index){
    index = index || 0;
    console.log("Req times: ", index);

    request({
        url: scan_url + index,
        method: "get",
        headers: headers,
        timeout: 10000,
    }, function (err, res, body) {
        if (err) {
            logging.error("Error happend, index: " + index + ", err: " + err.toString());
            setTimeout(function () {roomScaner(index)}, 500);
            return;
        }
        let r = JSON.parse(body).data || [];
        for (let i = 0; i < r.length; i++){
            MONITOR_ROOM_LIST.add(parseInt(r[i].roomid));
        }
        if (r.length > 0){
            EMPTY_PAGES_COUNT = 0;
        }else{
            EMPTY_PAGES_COUNT += 1;
        }

        if (index > 10 || EMPTY_PAGES_COUNT > 2) {
            console.log("Room length: ", MONITOR_ROOM_LIST.size);
            setRoomList(MONITOR_ROOM_LIST);
        }else{
            setTimeout(function () {roomScaner(index + 1)}, 10);
        }
    });
}


function setRoomList(room_list) {
    let finnal_list = Array.from(room_list).slice(0, ROOM_COUNT_LIMIT);
    fs.writeFile('./data/rooms.txt', Array.from(finnal_list).join("_"), function(err){
        if(err){
          logging.info("获取失败: " + err.toString());
        }else{
          logging.info("获取成功！finnal_list length: " + finnal_list.length);
        }
    });
}

roomScaner();
