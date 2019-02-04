let path = require('path');
let proj_config = require("../config/proj_config");
let env = proj_config.env;

let loggerFilePath = env === "server" ? "/home/wwwroot/log/" : "../log/";

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
        guardlistener: {
            type: 'file',
            filename: path.join(loggerFilePath, "guardlistener.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        recorder: {
            type: 'file',
            filename: path.join(loggerFilePath, "recorder.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        dosign: {
            type: 'file',
            filename: path.join(loggerFilePath, "dosign.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        heartbeat: {
            type: 'file',
            filename: path.join(loggerFilePath, "heartbeat.log"),
            maxLogSize: 1024*1024*50,
            backups: 2,
        },
        console: {type: 'console'}
    },
    categories: {
        chat: { appenders: ['console', "chat", "mix"], level: 'ALL'},
        gold: { appenders: ['console', "gold", "mix", "gift"], level: 'ALL'},
        sliver: { appenders: ['console', "sliver", "mix", "gift"], level: 'ALL'},

        acceptor: { appenders: ['console', "acceptor"], level: 'ALL'},
        apz_tv: { appenders: ['console', "apz_tv", "apz_default"], level: 'ALL'},
        apz_guard: { appenders: ['console', "apz_guard", "apz_default"], level: 'ALL'},
        apz_other_users: { appenders: ['console', "apz_other_users"], level: 'ALL'},
        guardlistener: { appenders: ['console', "guardlistener"], level: 'ALL'},
        recorder: { appenders: ['console', "recorder"], level: 'ALL'},

        dosign: { appenders: ['console', "dosign"], level: 'ALL'},
        heartbeat: { appenders: ['console', "heartbeat"], level: 'ALL'},

        default: { appenders: ['console'], level: 'ALL'}
    }
};

let log4js = require("log4js");
log4js.configure(config);

module.exports.chat = log4js.getLogger("chat");
module.exports.gold = log4js.getLogger("gold");
module.exports.sliver = log4js.getLogger("sliver");

module.exports.apz_tv = log4js.getLogger("apz_tv");
module.exports.apz_guard = log4js.getLogger("apz_guard");
module.exports.apz_other_users = log4js.getLogger("apz_other_users");

module.exports.acceptor = log4js.getLogger("acceptor");
module.exports.guardlistener = log4js.getLogger("guardlistener");
module.exports.recorder = log4js.getLogger("recorder");

module.exports.dosign = log4js.getLogger("dosign");
module.exports.heartbeat = log4js.getLogger("heartbeat");

module.exports.default = log4js.getLogger("default");