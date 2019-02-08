let path = require('path');
let proj_config = require("../config/proj_config");
let env = proj_config.env;

let loggerFilePath = env === "server" ? "/home/wwwroot/log/hansy" : "../log/";

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

module.exports.dosign = log4js.getLogger("dosign");
module.exports.heartbeat = log4js.getLogger("heartbeat");

module.exports.default = log4js.getLogger("default");