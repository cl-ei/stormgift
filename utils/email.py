import smtplib
import traceback
from email.mime.text import MIMEText
from config import mail_auth_pass


def send_email(subject, content, to, sender="80873436@qq.com"):
    to = [email_addr.strip() for email_addr in to]

    msg = MIMEText(content)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ",".join(to)

    s = smtplib.SMTP_SSL("smtp.qq.com", 465)
    error_message = ""
    try:
        s.login(sender, mail_auth_pass)
        s.sendmail(sender, to, msg.as_string())
    except Exception as e:
        error_message = f"Cannot send email: {e}. \n{traceback.format_exc()}"
    finally:
        s.quit()

    flag = False if error_message else True
    return flag, error_message


def send_cookie_invalid_notice(cookie_obj):
    user_name = cookie_obj.name
    uid = cookie_obj.user_id
    email_addr = cookie_obj.notice_email

    subject = f"{user_name}(uid: {uid}): 你配置的挂辣条登录信息已过期"
    content = f"{user_name}, 你配置的登录信息已过期, 如果需要继续挂辣条，你需要重新登录。"
    to = (email_addr, "80873436@qq.com") if email_addr else ("80873436@qq.com", )
    send_email(subject=subject, content=content, to=to)


def send_cookie_relogin_notice(cookie_obj):
    user_name = cookie_obj.name
    uid = cookie_obj.user_id

    subject = f"{user_name}(uid: {uid}): 已重新登录。"
    content = f"{user_name}, 已重新登录。"
    to = ("80873436@qq.com", )
    send_email(subject=subject, content=content, to=to)


def test():
    email_addr = "310300788@qq.com"
    user_name = "test"
    uid = 10109

    subject = f"{user_name}(uid: {uid}): 你配置的挂辣条登录信息已过期"
    content = f"{user_name}, 你配置的登录信息已过期, 现在可以重新登录。"
    to = (email_addr, "i@caoliang.net")
    r = send_email(subject=subject, content=content, to=to)
    print("r: ", r)


if __name__ == "__main__":
    test()
