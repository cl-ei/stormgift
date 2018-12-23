let request = require("request");
let logger = require("./utils/logger");
let DEBUG = !(process.argv.splice(2)[0] === "server");


let logging = logger.creatLogger('dosign', DEBUG ? "./log/" : "/home/wwwroot/log/");
let UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36';
let RAW_COOKIES_LIST = require('./data/cookie.js').RAW_COOKIE_LIST;


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
                logging.info("doSign Success! index: %d, ", index);
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
                let r = JSON.parse(body.toString());
                if(r.code === 0){
                    logging.info("DoJoin success! index: %s, group_name: %s", index, group_name)
                }else{
                    logging.info("doSign Error! index: %d, group name: %s, r: %s", index, group_name, body.toString());
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
                logging.info("doSign Error! index: %d, r: %s", index, body.toString());
            }
        }
    });
};

(() => {
    logging.info("Start doSign proc, ENV: %s", DEBUG ? "DEBUG": "SERVER");
    for (let i = 0; i < RAW_COOKIES_LIST.length; i++){
        let c = RAW_COOKIES_LIST[i];
        doSign(c, i);
        signGroup(c, i);
    }
})();
