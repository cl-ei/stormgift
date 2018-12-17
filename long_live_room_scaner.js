let request = require("request");
let fs = require("fs");
let log4js = require('log4js');
let DEBUG = !(process.argv.splice(2)[0] === "server");


let logerconf = {
  appenders: {
    long_live_scaner: {
      type: 'file',
      filename: DEBUG ? './log/long_live_scaner.log' : "/home/wwwroot/log/storm/long_live_scaner.log",
      maxLogSize: 102400,
      backups: 10,
    },
    console: { type: 'console' }
  },
  categories: {
    long_live_scaner: { appenders: ['long_live_scaner', 'console'], level: 'ALL' },
    default: { appenders: ['long_live_scaner', 'console'], level: 'trace' }
  }
};

log4js.configure(logerconf);
let logging = log4js.getLogger('long_live_scaner');

let scan_url = "https://api.live.bilibili.com/room/v1/room/get_user_recommend?page=";
let UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36';
let headers = {'User-Agent': UA};
let ROOM_DICT = {};
let ROOM_DICT_FILE_NAME = "./longliveroomjson.json";
try{
    ROOM_DICT = JSON.parse(fs.readFileSync(ROOM_DICT_FILE_NAME, "utf-8"));
}catch (e) {}
console.log(ROOM_DICT);


function roomScaner(index, EMPTY_PAGES_COUNT){
    EMPTY_PAGES_COUNT = EMPTY_PAGES_COUNT || 0;
    index = index || 0;
    console.log("Req times: ", index);

    request({
        url: scan_url + index,
        method: "get",
        headers: headers,
        timeout: 10000,
    }, function (err, res, body) {
        if (err) {
            setTimeout(function () {roomScaner(index, EMPTY_PAGES_COUNT)}, 500);
            return;
        }

        let r = JSON.parse(body).data || [];
        for (let i = 0; i < r.length; i++){
            let room_id = parseInt(r[i].roomid);
            let online = parseInt(r[i].online);
            if (room_id in ROOM_DICT){
                ROOM_DICT[room_id].o.push(online);
            }else {
                ROOM_DICT[room_id] = {o: [online]}
            }
        }
        if (r.length > 0){
            EMPTY_PAGES_COUNT = 0;
        }else{
            EMPTY_PAGES_COUNT += 1;
        }

        if (index < 500 && EMPTY_PAGES_COUNT < 4) {
            setTimeout(function () {roomScaner(index + 1);}, 1500);
        }else{
            fs.writeFile(ROOM_DICT_FILE_NAME, JSON.stringify(ROOM_DICT), function(err){
                if(err){
                    logging.info("获取失败: " + err.toString());
                }else{
                    logging.info("获取成功！total: " + Object.keys(ROOM_DICT).length + ", req times: " + index);
                }
            });
        }
  });
}

roomScaner();
