function generatePacket (action, payload) {
    payload = payload || '';
    let packetLength = Buffer.byteLength(payload) + 16;
    let buff = new Buffer.alloc(packetLength);

    buff.writeInt32BE(packetLength, 0);
    // write consts
    buff.writeInt16BE(16, 4);
    buff.writeInt16BE(1, 6);
    buff.writeInt32BE(1, 12);
    // write action
    buff.writeInt32BE(action, 8);
    // write payload
    buff.write(payload, 16);
    return buff
}

function sendJoinRoom(client, rid){
    let uid = 1E15 + Math.floor(2E15 * Math.random());
    let packet = JSON.stringify({uid: uid, roomid: rid});
    let joinedRoomPayload = generatePacket(7, packet);
    client.send(joinedRoomPayload);
}

function parseMessage(arrayBuffer, room_id, procFn, failedFn){
    if(arrayBuffer.byteLength < 21) {return}

    let buff = Buffer.from(arrayBuffer);
    let view = new Uint8Array(arrayBuffer);
    for (let i = 0; i < buff.length; ++i) {buff[i] = view[i]}
    while (buff.length > 16){
        let length = (buff[0] << 24) + (buff[1] << 16) + (buff[2] << 8) + buff[3];
        let current = buff.slice(0, length);
        buff = buff.slice(length);
        if (current.length > 16 && current[16] !== 0){
            try{
                let msg = JSON.parse("" + current.slice(16));
                procFn(msg, room_id);
            }catch (e) {
                (failedFn || function(e){})("e: " + current);
            }
        }
    }
}


let HEART_BEAT = generatePacket(2);
let MONITOR_URL = "ws://broadcastlv.chat.bilibili.com:2244/sub";

exports.MONITOR_URL = MONITOR_URL;
exports.HEART_BEAT_PACKAGE = HEART_BEAT;
exports.parseMessage = parseMessage;
exports.sendJoinRoom = sendJoinRoom;
