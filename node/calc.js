let fs = require("fs");
let logfile = "./log/gold.log";

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