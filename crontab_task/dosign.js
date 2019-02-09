let loggerFilePath = "/home/wwwroot/log/";
let log_config = {
    appenders: {
        dosign: {
            type: 'file',
            filename: path.join(loggerFilePath, "dosign.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        console: {type: 'console'}
    },
    categories: {
        dosign: { appenders: ['console', "dosign"], level: 'ALL'},
        default: { appenders: ['console'], level: 'ALL'}
    }
};
let log4js = require("log4js");
log4js.configure(log_config);
let logging = log4js.getLogger("dosign");


let request = require("request");
let UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36';
let fs = require("fs");
let COOKIE_FILE_PATH = '/home/wwwroot/stormgift/data/cookie.json';
let RAW_COOKIES_LIST = JSON.parse(fs.readFileSync(COOKIE_FILE_PATH, "utf-8")).RAW_COOKIE_LIST;


let doSign = (cookie, index) => {
    request.get({
        url: "https://api.live.bilibili.com/sign/doSign",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 10000,
    }, function (err, res, body) {
        if (err) {
            logging.error("Do sign error, index: %d, e: %s", index, err.toString());
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                // logging.info("doSign Success! index: %d, ", index);
            }else{
                logging.info("doSign Error! index: %d, r: %s", index, body.toString());
            }
        }
    });
};
let signGroup = (cookie, index) => {
    let joinGroup = (group_id, owner_id, group_name) => {
        request({
            url: "https://api.live.bilibili.com/link_setting/v1/link_setting/sign_in",
            headers: {"User-Agent": UA, "Cookie": cookie},
            timeout: 10000,
            method: "post",
            form: {
                group_id: group_id,
                owner_id: owner_id
            }
        }, function (err, res, body) {
            if (err) {
                logging.error("JoinGroup error, index: %d, e: %s", index, err.toString());
            }else{
                if(index !== 0){return}
                let r = JSON.parse(body.toString());
                if(r.code === 0){
                    let add_num = r.data.add_num;
                    if(add_num > 0){
                        logging.info("DoJoin success! index: %s, add: %d, group_name: %s", index, add_num, group_name);
                    }else{
                        // logging.error("doSign add_num Error! index: %d, add_num: %d, group name: %s", index, add_num, group_name);
                    }
                }else{
                    logging.error("JoinGroup Error! index: %d, group name: %s, r: %s", index, group_name, body.toString());
                }
            }
        });
    };
    request.get({
        url: "https://api.live.bilibili.com/link_group/v1/member/my_groups",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 10000,
    }, function (err, res, body) {
        if (err) {
            logging.error("Do sign error, index: %d, e: %s", index, err.toString());
        }else{
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                let groupList = r.data.list;
                for(let i = 0; i < groupList.length; i++){
                    joinGroup(groupList[i].group_id, groupList[i].owner_uid, groupList[i].group_name)
                }
            }else{
                logging.error("Get groups to join Error! index: %d, r: %s", index, body.toString());
            }
        }
    });
};
let doubleWatchTask = (cookie, index) => {
    let cookie_kv = cookie.split(";");
    let csrf_token = "";
    for (let i = 0; i < cookie_kv.length; i++){
        let kvstr = cookie_kv[i];
        if (kvstr.indexOf("bili_jct") > -1){
            csrf_token = kvstr.split("=")[1].trim();
            break;
        }
    }
    if (csrf_token.length < 10){
        logging.error("Bad csrf token! index: %d.", index);
        return;
    }
    request({
        url: "https://api.live.bilibili.com/activity/v1/task/receive_award",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 10000,
        method: "post",
        form: {
            task_id: "double_watch_task",
            csrf_token: csrf_token,
            csrf: csrf_token,
        }
    }, function (err, res, body) {
        if (err) {
            logging.error("doubleWatchTask error, index: %d, e: %s", index, err.toString());
        }else{
            if(index !== 0){return}
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                logging.info("doubleWatchTask success! index: %s", index)
            }else{
                // logging.info("doubleWatchTask Error! index: %d, r: %s", index, body.toString());
            }
        }
    });
};
let silverToCoin = (cookie, index) => {
    let csrf_token = "",
        cookie_kv = cookie.split(";");
    for (let i = 0; i < cookie_kv.length; i++){
        let kvstr = cookie_kv[i];
        if (kvstr.indexOf("bili_jct") > -1){
            csrf_token = kvstr.split("=")[1].trim();
            break;
        }
    }

    let reqParam = {
        url: "https://api.live.bilibili.com/pay/v1/Exchange/silver2coin",
        headers: {"User-Agent": UA, "Cookie": cookie},
        timeout: 10000,
        method: "post",
        form: {
            platform: "pc",
            csrf_token: csrf_token
        }
    },
    cbFn = (err, res, body) => {
        if (err) {
            logging.error("silverToCoin error, index: %d, e: %s", index, err.toString());
        }else{
            if(index !== 0){return}
            let r = JSON.parse(body.toString());
            if(r.code === 0){
                // logging.info("silverToCoin succeed! sliver: %s", (r.data || {}).silver);
            }else{
                logging.error("silverToCoin Failed! r: %s", body.toString());
            }
        }
    };
    request(reqParam, cbFn);
};

(() => {
    for (let i = 0; i < RAW_COOKIES_LIST.length; i++){
        let c = RAW_COOKIES_LIST[i];
        doSign(c, i);
        signGroup(c, i);
        doubleWatchTask(c, i);
        if(i <= 1){
            silverToCoin(RAW_COOKIES_LIST[i], i);
        }
    }
})();
