let chokidar = require('chokidar');
let fs = require("fs");
let http = require('http');
let WebSocketServer = require('websocket').server;

MONITOR_LOG_FILE = "/home/wwwroot/log/stormgift.log";
MONITOR_HOST = "0.0.0.0";
MONITOR_PORT = 22223;

let Monitor = {
    __FILE_POS: 0,
    __cbFn: undefined,

    getFileSize: (path_) => {
        return fs.statSync(path_).size;
    },
    onFileChanged: (path_) => {
        let oldPos = Monitor.__FILE_POS;
        Monitor.__FILE_POS = Monitor.getFileSize(path_);
        oldPos = (oldPos < Monitor.__FILE_POS) ? oldPos : Monitor.__FILE_POS;

        fs.createReadStream(path_,{start: oldPos, end: Monitor.__FILE_POS}).on('data',function(data){
            if(Monitor.__cbFn !== undefined){Monitor.__cbFn(data)}
        });
    },
    init: (cbFb) => {
        fs.exists(MONITOR_LOG_FILE, (existed) => {
            let monitorFile = existed ? MONITOR_LOG_FILE : "log/stormgift.log";

            Monitor.__FILE_POS = Monitor.getFileSize(monitorFile);
            Monitor.__cbFn = cbFb;
            chokidar.watch(monitorFile)
                .on('change', Monitor.onFileChanged)
                .on('error', (e) => {throw e})
                .on('ready', () => {console.log('Ready.')});
        });
    },
};

let __connectedClients = new Set();
let noticeToAll = (msg) => {
    __connectedClients.forEach((c) => {
        try{
            c.sendUTF(msg);
        }catch (e) {
            console.log("Error happened when broadcast log, e: %s", e.toString())
        }
    });
};

let startServer = () => {
    let server = http.createServer(function(request, response) {
        response.writeHead(404);
        response.end();
    });
    server.listen(MONITOR_PORT, MONITOR_HOST, () => {
        console.log(
            "Log Broadcaster is listening on ws://%s:%s",
            MONITOR_HOST, MONITOR_PORT
        )
    });

    let wsServer = new WebSocketServer({httpServer: server, autoAcceptConnections: false});
    wsServer.on('request', function(request) {
        let connection = request.accept();
        console.log(
            'Log Server accept a new client, addr: %s, port: %s.',
            connection.remoteAddress, connection.socket.remotePort
        );
        connection.on('close', function(reasonCode, description) {
            console.log(
                'Log Server disconnect a client: %s:%s, r: %s, des: %s',
                connection.remoteAddress, connection.socket.remotePort, reasonCode, description
            );
            __connectedClients.delete(connection);
        });
        connection.sendUTF("Log server has been connected. your ip is " + connection.remoteAddress + ", transferring data...\n");
        __connectedClients.add(connection);
    });
};

(() => {
    startServer();
    Monitor.init((data) => {noticeToAll(data)});
})();
