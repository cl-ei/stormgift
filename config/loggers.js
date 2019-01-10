let path = require('path');
let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let loggerFilePath = DEBUG ? "./log/" : "/home/wwwroot/log/";
let config = {
    appenders: {
        gold: {
            type: 'file',
            filename: path.join(loggerFilePath, "gold.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        sliver: {
            type: 'file',
            filename: path.join(loggerFilePath, "sliver.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        gift: {
            type: 'file',
            filename: path.join(loggerFilePath, "gift.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        mix: {
            type: 'file',
            filename: path.join(loggerFilePath, "mix.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        chat: {
            type: 'file',
            filename: path.join(loggerFilePath, "chat.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
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
        chat: { appenders: ['console', "chat", "mix"], level: 'ALL'},
        gold: { appenders: ['console', "gold", "mix", "gift"], level: 'ALL'},
        sliver: { appenders: ['console', "sliver", "mix", "gift"], level: 'ALL'},

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
