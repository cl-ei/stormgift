let net = require('net');

let onMessageReceived = (msg, addr) => {
    console.log("Msg: %s", msg);
};

(() => {
    let connectionListener = (sock) => {
        console.log('New client connected: addr: %s, port: %s', sock.remoteAddress, sock.remotePort);
        sock.on('data', function(data) {
            console.log('Server received: ' + sock.remoteAddress + ': ' + data);
            sock.write('You said "' + data + '"');
        });
        sock.on('close', function(data) {
            console.log('Client closed: addr: %s, port: %s, data: %s', sock.remoteAddress, sock.remotePort, data);
        });
    };
    let server = net.createServer(connectionListener);
    server.listen(11111, "0.0.0.0");
})();


setTimeout(function(){
    let client = new net.Socket();
    let clientConnectionListener = (client) => {
        console.log('CONNECTED TO: ');
        client.on('data', function(data) {
            console.log('Client received: ' + data);
        });
        client.on('close', function() {
            console.log('Connection closed');
            client.connect(11111, "localhost");
        });
    };
    client.connect(11111, "localhost", function() {clientConnectionListener(client)});

    client.write("123__");
    setTimeout(() => {
        client.destroy();
        setTimeout(() => {client.write("old")}, 2000);
    }, 5000)
}, 2000);

