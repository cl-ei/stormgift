let net = require('net');
let logger = require("./utils/logger");

let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let logging = logger.creatLogger('prizehandler', DEBUG ? "./log/" : "/home/wwwroot/log/");
logging.info("Start proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));
let prizeRec = logger.creatLogger('prizerec', DEBUG ? "./log/" : "/home/wwwroot/log/");

let onMessageReceived = (msg, addr) => {
    console.log("Message received: %s", msg);
    if (msg.length < 5 || msg[0] !== "_"){return}
    let giftType = msg[1],
        room_id = parseInt(msg.slice(2));
    console.log("Message received: %s, giftType: %s", room_id, giftType);
    if(giftType === "S"){
        prizeRec.info("Gift: %s, room_id: %s", giftType, room_id);
    }else if(giftType === "G"){
        prizeRec.info("Gift: %s, room_id: %s", giftType, room_id);
    }else if(giftType === "T"){
        prizeRec.info("Gift: %s, room_id: %s", giftType, room_id);
    }
};

(() => {
    let connectionListener = (sock) => {
        logging.info('New client connected: addr: %s, port: %s', sock.remoteAddress, sock.remotePort);
        sock.on('data', function(data) {onMessageReceived(data, sock.remoteAddress)});
        sock.on('close', function(data) {
            logging.error('Client closed: addr: %s, port: %s, data: %s', sock.remoteAddress, sock.remotePort, data);
        });
    };
    net.createServer(connectionListener).listen(11111, "0.0.0.0");
})();
