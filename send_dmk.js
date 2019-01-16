let damakusender = require("./utils/danmakusender");
let logging = require("./config/loggers").default;
let dmksender = new damakusender.Sender(0, logging);

let sysArgs = process.argv.splice(2);
let message = sysArgs[0];
if(message){
    console.log("send: %s", message);
    dmksender.sendDamaku(message, 2516117);
}

