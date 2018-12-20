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
