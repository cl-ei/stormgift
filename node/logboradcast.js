let chokidar = require('chokidar');
let fs = require("fs");
let http = require('http');
let WebSocketServer = require('websocket').server;
let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let Monitor = {
    MONITOR_LOG_FILE: DEBUG ? "./log/stormgift.log" : "/home/wwwroot/log/supervisor/stormgift.log",
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
        Monitor.__FILE_POS = Monitor.getFileSize(Monitor.MONITOR_LOG_FILE);
        Monitor.__cbFn = cbFb;
        chokidar.watch(Monitor.MONITOR_LOG_FILE)
            .on('change', Monitor.onFileChanged)
            .on('error', (e) => {throw e})
            .on('ready', () => {console.log('Ready.')});
    },
};

let __connectedClients = new Set();
let noticeToAll = (msg) => {
    __connectedClients.forEach((c) => {
        try{
            c.sendUTF(msg);
        }catch (e) {
            console.log("Cannot send prize message to acceptor client, e: %s", e.toString())
        }
    });
};

let startServer = () => {
    let server = http.createServer(function(request, response) {
        response.writeHead(404);
        response.end();
    });
    server.listen(22223, "0.0.0.0", () => {console.log('Log Server is listening on port 22223')});

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
        __connectedClients.add(connection);
    });
};

(() => {
    startServer();
    Monitor.init((data) => {noticeToAll(data)});
})();
