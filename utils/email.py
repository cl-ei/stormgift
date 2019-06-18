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
