import smtplib
import traceback
from email.mime.text import MIMEText
from config import mail_auth_pass


def send_email(subject, to=""):
    to = to.strip()
    if not to:
        return

    user = "80873436@qq.com"

    msg = MIMEText("挂辣条登录已过期，请重新设置。")
    msg['Subject'] = subject or "-"
    msg['From'] = user
    msg['To'] = to

    s = smtplib.SMTP_SSL("smtp.qq.com", 465)
    error_message = ""
    try:
        s.login(user, mail_auth_pass)
        s.sendmail(user, to, msg.as_string())
    except Exception as e:
        error_message = f"Cannot send email: {e}. {traceback.format_exc()}"
    finally:
        s.quit()

    flag = False if error_message else True
    return flag, error_message


def send_cookie_invalid_notice(cookie):
    email_addr = ""
    for c in cookie.split(';'):
        if "notice_email" in c:
            email_addr = c.split("=")[-1].strip()
            break

    if email_addr:
        send_email(f"辣条-登录信息已过期：\n{cookie}", email_addr)
        send_email(f"辣条-登录信息已过期：\n{cookie}", "310300788@qq.com")


if __name__ == "__main__":
    r = send_email("測試", "80873436@qq.com")
    print(r)
