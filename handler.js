let net = require('net');
let logger = require("./utils/logger");
let http = require('http');
let WebSocketServer = require('websocket').server;

let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let loggerFilePath = DEBUG ? "./log" : "/home/wwwroot/log";
let logging = logger.creatLogger("handler", loggerFilePath);
logging.info("Start proc -> env: " + (DEBUG ? "DEBUG" : "SERVER"));


let __connectedClients = new Set();
let noticeToAll = (msg) => {
    __connectedClients.forEach((c) => {
        try{
            logging.info("\tPRIZE_MSG [%s] -> (%s:%s)", msg, c.remoteAddress, c.socket.remotePort);
            c.sendUTF("" + msg);
        }catch (e) {
            logging.error("Cannot send prize message to acceptor client, e: %s", e.toString())
        }
    });
};
let startNoticeServer = () => {
    let server = http.createServer(function(request, response) {
        logging.info('NoticeServer received request for ' + request.url);
        response.writeHead(404);
        response.end();
    });
    server.listen(11112, () => {logging.info('NoticeServer Server is listening on port 11112')});

    let wsServer = new WebSocketServer({
        httpServer: server,
        // You should not use autoAcceptConnections for production
        // applications, as it defeats all standard cross-origin protection
        // facilities built into the protocol and the browser.  You should
        // *always* verify the connection's origin and decide whether or not
        // to accept it.
        autoAcceptConnections: false
    });

    wsServer.on('request', function(request) {
        let connection = request.accept();
        logging.info(
            'Acceptor client accepted, addr %s, port: %s.',
            connection.remoteAddress, connection.socket.remotePort
        );
        connection.on('close', function(reasonCode, description) {
            logging.info(
                'Acceptor client %s:%s disconnected, r: %s, des: %s',
                connection.remoteAddress, connection.socket.remotePort, reasonCode, description
            );
            __connectedClients.delete(connection);
            logging.info("Exist __connectedClients: %s.\n", __connectedClients.size)
        });
        __connectedClients.add(connection);
    });
};

let startPrizeMessageReceiver = () => {
    let connectionListener = (sock) => {
        if(sock.remoteAddress !== "127.0.0.1" && sock.remoteAddress !== "47.104.176.84"){
            logging.error("ERROR ! Close connections without authentication! <- %s:%s", sock.remoteAddress, sock.remotePort);
            sock.destroy();
            return;
        }
        logging.info('New prize message source added, addr: %s, port: %s', sock.remoteAddress, sock.remotePort);
        sock.on('data', function(data) {
            logging.info("Received prize message from source: %s", data);
            try{noticeToAll(data)}catch(e){
                logging.error("Proc prize message coursed an error: %s", e.toString())
            }
        });
        sock.on('close', function(data) {
            logging.info('Prize message source closed: addr: %s, port: %s', sock.remoteAddress, sock.remotePort);
        });
    };
    net.createServer(connectionListener).listen(11111, "0.0.0.0");
};


(() => {
    startNoticeServer();
    startPrizeMessageReceiver();
})();
