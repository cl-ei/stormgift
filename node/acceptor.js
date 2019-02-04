let W3CWebSocket = require('websocket').w3cwebsocket;

let logging = require("./config/loggers").acceptor;
logging.info("Start acceptor proc.");


let Gac = require("./utils/guard_acceptor_directly").Acceptor;
let Tac = require("./utils/tvacceptor").Acceptor;

let onMessageReceived = (msg) => {
    let source = msg[0],
        giftType = msg[1],
        msgBody = msg.slice(2);

    if(source === "N" && giftType === "G"){
        Gac.accept(msgBody);

    }else if(giftType === "T"){
        Tac.accept(parseInt(msgBody));
    }
};


(() => {
    let ConnectToNoticeServer = () => {
        let client = new W3CWebSocket("ws://127.0.0.1:11112");
        client.onerror = () => {
            logging.error("Connection to notice server error! Try reconnect...");
            client.onclose = undefined;
            setTimeout(ConnectToNoticeServer, 500);
        };
        client.onopen = () => {
            function sendHeartBeat() {
                if (client.readyState === client.OPEN){
                    client.send("HEARTBEAT");
                    setTimeout(sendHeartBeat, 10000);
                }
            }
            sendHeartBeat();
        };
        client.onclose = () => {
            logging.error("ConnectToNoticeServer closed! Try reconnect...");
            setTimeout(ConnectToNoticeServer, 500);
        };
        client.onmessage = (e) => {
            let mList = e.data.match(/(_T|_G|XG|_S|NG)\d{2,}\$?\d+/g) || [];
            for(let i = 0; i < mList.length; i++){onMessageReceived(mList[i])}
        };
    };
    ConnectToNoticeServer();
})();
