let log4js = require("log4js");
let path = require('path');

exports.creatLogger = function(loggerName, path_){
    let config = {
        appenders: {console: { type: 'console' }},
        categories: {default: { appenders: ['console'], level: 'trace' }}
    };
    config.appenders[loggerName] = {
        type: 'file',
        filename: path.join(path_, loggerName+ ".log"),
        maxLogSize: 1024*1024*200,
        backups: 2,
    };
    config.categories[loggerName] = {appenders: [loggerName, 'console'], level: 'ALL' };
    log4js.configure(config);
    return log4js.getLogger(loggerName);
};


exports.batchCreateLogger = function(configList){
    let loggerNameList = [];
    let config = {
        appenders: {console: { type: 'console' }},
        categories: {default: { appenders: ['console'], level: 'trace' }}
    };
    for (let i = 0; i < configList.length; i++){
        let loggerName = configList[i].loggerName,
            loggerFile = configList[i].loggerFile;

        loggerNameList.push(loggerName);
        config.appenders[loggerName] = {
            type: 'file',
            filename: loggerFile,
            maxLogSize: 1024*1024*200,
            backups: 2,
        };
        config.categories[loggerName] = {
            appenders: [loggerName, 'console'], level: 'ALL'
        };
    }
    log4js.configure(config);
    let loggerList = {};
    for (let i = 0; i < loggerNameList.length; i++){
        loggerList[loggerNameList[i]] = log4js.getLogger(loggerNameList[i]);
    }
    return loggerList;
};
