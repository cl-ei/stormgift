let path = require('path');
let env = process.env.NODE_ENV;

console.log("Config log4js env: %s.", env);
let loggerFilePath = env === "server" ? "/home/wwwroot/log/" : "./log/";

let config = {
    appenders: {
        acceptor: {
            type: 'file',
            filename: path.join(loggerFilePath, "acceptor.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        apz_default: {
            type: 'file',
            filename: path.join(loggerFilePath, "apz_default.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        apz_tv: {
            type: 'file',
            filename: path.join(loggerFilePath, "apz_tv.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        apz_guard: {
            type: 'file',
            filename: path.join(loggerFilePath, "apz_guard.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        apz_other_users: {
            type: 'file',
            filename: path.join(loggerFilePath, "apz_other_users.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        console: {type: 'console'}
    },
    categories: {
        acceptor: { appenders: ['console', "acceptor"], level: 'ALL'},
        apz_tv: { appenders: ['console', "apz_tv", "apz_default"], level: 'ALL'},
        apz_guard: { appenders: ['console', "apz_guard", "apz_default"], level: 'ALL'},
        apz_other_users: { appenders: ['console', "apz_other_users"], level: 'ALL'},

        default: { appenders: ['console'], level: 'ALL'}
    }
};

let log4js = require("log4js");
log4js.configure(config);

module.exports.apz_tv = log4js.getLogger("apz_tv");
module.exports.apz_guard = log4js.getLogger("apz_guard");
module.exports.apz_other_users = log4js.getLogger("apz_other_users");

module.exports.acceptor = log4js.getLogger("acceptor");
module.exports.default = log4js.getLogger("default");
