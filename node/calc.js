let fs = require("fs");
let sysArgs = process.argv.splice(2);
let DEBUG = !(sysArgs[0] === "server");

let logfile = DEBUG ? "./log/gold.log" : '/home/wwwroot/log/lyy/gold.log';

fs.readFile(logfile, "utf-8", (err, data) => {
    if (err) {
        console.log("Error happend when reading file, err: " + err.toString());
        return
    }
    let priceList = data.match(/\(\d+\)/g),
        total = 0;
    for (let i = 0; i < priceList.length; i++){
        total += parseInt(priceList[i].slice(1))
    }
    console.log(total/1000);
});
