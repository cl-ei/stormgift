let request = require("request");
let redis = require("redis");
let W3CWebSocket = require('websocket').w3cwebsocket;
let proj_config = require("./config/proj_config");
let env = proj_config.env;
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36";

let logging = require("./config/loggers").tvrecorder;
logging.info("Start tvrecorder proc.");

let DataAccess = {
    redis_client: undefined,
    save: (key, data) => {
        if (DataAccess.redis_client === undefined){
            setTimeout(() => {DataAccess.save(key, data)}, 1000);
            return
        }

        DataAccess.redis_client.get(key, (e, d) => {
            if(e !== null){
                logging.error("Error happened when get k: %s", key);
                return;
            }
            if(d === null){
                DataAccess.redis_client.set(key, data, (e, reason) => {
                    if(e !== null){
                        logging.error(
                            "Error happened when set, e: %s, k: %s, data: %s, reason: %s.",
                            e.toString(), key, data, reason
                        );
                        setTimeout(() => {DataAccess.save(key, data)}, 1000);
                    }
                });
            }
        });
    },
    init: () => {
        let rc = redis.createClient(
            proj_config.redis.port,
            proj_config.redis.host,
            {auth_pass: proj_config.redis.auth_pass, db: proj_config.redis.db}
        );
        rc.on('connect',function(){
            DataAccess.redis_client = rc;
            console.log('Redis client connected.');
        });
    }
};

let Recoreder = {
    getDetail: (room_id) => {
        let reqParam = {
            url: "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=" + room_id,
            method: "get",
            headers: {"User-Agent": UA},
            timeout: 20000,
        },
        cbFn = (err, res, body) => {
            if (err) {
                logging.error("Get tv gift id error: %s, room_id: %s", err.toString(), room_id);
                return;
            }
            let r = {"-": "-"};
            try {
                r = JSON.parse(body.toString());
            } catch (e) {
                logging.error("Error response getTvGiftId: %s, body:\n-------\n%s\n\n", e.toString(), body);
                return;
            }
            if (r.code !== 0) {return}
            let data = r.data || {};
            let gidlist = data.list || [];
            for (let i = 0; i < gidlist.length; i++) {
                let info = gidlist[i];
                let key = "_T" + room_id + "$" + info.raffleId;

                info._saved_time = (new Date()).valueOf();
                let saveData = JSON.stringify(info);

                logging.debug("SAVE: key: %s, data: %s", key, saveData);
                DataAccess.save(key, saveData);
            }
        };
        request(reqParam, cbFn);
    },
    procMessage: (msg) => {
        let source = msg[0],
            giftType = msg[1],
            msgBody = msg.slice(2);

        if(giftType === "T"){
            let room_id = parseInt(msgBody);
            console.log("room_id: %s", room_id);

            Recoreder.getDetail(room_id);
        }
    },
};


(() => {
    DataAccess.init();
    let ConnectToNoticeServer = () => {
        let client = new W3CWebSocket(env === "server" ? "ws://127.0.0.1:11112" : "ws://129.204.43.2:11112");
        client.onerror = () => {
            logging.error("Connection to notice server error! Try reconnect...");
            client.onclose = undefined;
            setTimeout(ConnectToNoticeServer, 500);
        };
        client.onopen = () => {
            function sendHeartBeat() {
                if (client.readyState === client.OPEN){
                    client.send("HEARTBEAT");
                    setTimeout(sendHeartBeat, 10000);
                }
            }
            sendHeartBeat();
        };
        client.onclose = () => {
            logging.error("ConnectToNoticeServer closed! Try reconnect...");
            setTimeout(ConnectToNoticeServer, 500);
        };
        client.onmessage = (e) => {
            let mList = e.data.match(/(_T|_G|XG|_S|NG)\d{2,}\$?\d+/g) || [];
            for(let i = 0; i < mList.length; i++){Recoreder.procMessage(mList[i])}
        };
    };
    ConnectToNoticeServer();
})();
