let request = require("request");
let fs = require("fs");
let log4js = require('log4js');
let DEBUG = !(process.argv.splice(2)[0] === "server");
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

let MONITOR_ROOM_LIST = {};
let scan_url = "https://api.live.bilibili.com/room/v1/room/get_user_recommend?page=";
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
        let room_id = parseInt(r[i].roomid);
        let online = parseInt(r[i].online);
        MONITOR_ROOM_LIST[room_id] = online;
      }
      if (r.length > 0){
        EMPTY_PAGES_COUNT = 0;
      }else{
        EMPTY_PAGES_COUNT += 1;
      }

      if (index > 300 || EMPTY_PAGES_COUNT > 5) {
        console.log("Room length: ", Object.keys(MONITOR_ROOM_LIST).length);
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
  function sortNumber(a, b){return b - a}
  let online_list = Object.values(room_list);
  online_list.sort(sortNumber);

  let finnal_list = [];
  let level = online_list[1500];
  console.log("Level: ", level);
  for (let room_id in room_list){
    if(room_list[room_id] > level){
      finnal_list.push(room_id);
    }
  }
  fs.writeFile('./rooms.txt', Array.from(finnal_list).join("_"), function(err){
      if(err){
        logging.info("获取失败: " + err.toString());
      }else{
        logging.info("获取成功！");
      }
  });
}

roomScaner();

console.log("Started.");
