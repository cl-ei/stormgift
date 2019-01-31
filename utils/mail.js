const nodemailer = require("nodemailer");
let proj_config = require("../config/proj_config");

let transporter = nodemailer.createTransport({
    service: "qq",
    port: 465,
    secureConnection: true,
    auth: {
        user: "luaguy@qq.com",
        pass: proj_config.mail_auth_pass,
    }
});

module.exports.sendMail = (subject, text, cb) => {
    transporter.sendMail({
        from: "辣条挂<luaguy@qq.com>",
        to: "luaguy@qq.com, calom@qq.com",
        subject: subject,
        text: text,
    }, cb);
};
