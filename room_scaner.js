let request = require("request");
let fs = require("fs");
let log4js = require('log4js');
let DEBUG = !(process.argv.splice(2)[0] === "server");
let ROOM_COUNT_LIMIT = 6000;
console.log("DEBUG env: ", DEBUG);

let logerconf = {
  appenders: {
    scaner: {
      type: 'file',
      filename: DEBUG ? './log/scaner.log' : "/home/wwwroot/log/storm/scaner.log",
      maxLogSize: 102400,
      backups: 10,
    },
    console: { type: 'console' }
  },
  categories: {
    scaner: { appenders: ['scaner', 'console'], level: 'ALL' },
    default: { appenders: ['scaner', 'console'], level: 'trace' }
  }
};

log4js.configure(logerconf);
let logging = log4js.getLogger('scaner');

let MONITOR_ROOM_LIST = new Set();
let scan_url = "https://api.live.bilibili.com/room/v1/Area/getListByAreaID?areaId=0&sort=online&pageSize=500&page=";
let headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'
};

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
      setTimeout(function () {
        roomScaner(index);
      }, 500);
    } else {
      let r = JSON.parse(body).data || [];
      for (let i = 0; i < r.length; i++){
        MONITOR_ROOM_LIST.add(parseInt(r[i].roomid));
      }
      if (r.length > 0){
        EMPTY_PAGES_COUNT = 0;
      }else{
        EMPTY_PAGES_COUNT += 1;
      }

      if (index > 10 || EMPTY_PAGES_COUNT > 5) {
        console.log("Room length: ", MONITOR_ROOM_LIST.size);
        setRoomList(MONITOR_ROOM_LIST);
      }else{
        setTimeout(function () {
          roomScaner(index + 1);
        }, 10);
      }
    }
  });
}


function setRoomList(room_list) {
  let finnal_list = Array.from(room_list).slice(0, ROOM_COUNT_LIMIT);
  fs.writeFile('./rooms.txt', Array.from(finnal_list).join("_"), function(err){
      if(err){
        logging.info("获取失败: " + err.toString());
      }else{
        logging.info("获取成功！finnal_list length: " + finnal_list.length);
      }
  });
}

roomScaner();

console.log("Started.");
