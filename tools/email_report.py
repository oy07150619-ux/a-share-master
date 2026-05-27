#!/usr/bin/env python3
"""
A股报告邮件发送工具
支持发送HTML正文 + PDF附件
"""

import smtplib
import os
import sys
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header

SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465
FROM_EMAIL = "1683881988@qq.com"
AUTH_CODE = "txqfajcelmzyfagi"
TO_EMAIL = "1683881988@qq.com"
REPORT_DIR = "/home/chris/.openclaw/workspace/reports"


def send_email(subject, html_body, attachments=None):
    """发送邮件"""
    msg = MIMEMultipart('alternative')
    msg['From'] = FROM_EMAIL
    msg['To'] = TO_EMAIL
    msg['Subject'] = Header(subject, 'utf-8')

    # HTML正文
    html_part = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(html_part)

    # 附件
    if attachments:
        for filepath in attachments:
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'rb') as f:
                        attachment = MIMEApplication(f.read())
                        filename = os.path.basename(filepath)
                        attachment.add_header('Content-Disposition', 'attachment', filename=('utf-8', '', filename))
                        msg.attach(attachment)
                except Exception as e:
                    print(f"附件失败: {filepath} - {e}", file=sys.stderr)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(FROM_EMAIL, AUTH_CODE)
        server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
    return True


def build_email(subject, body_lines):
    """构建HTML邮件正文"""
    lines = []
    in_code = False
    for line in body_lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            lines.append(f"<pre style='background:#f5f5f5;padding:8px;border-radius:4px;font-size:12px;'>{stripped}</pre>")
        elif stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip('#'))
            text = stripped.lstrip('#').strip()
            if level <= 2:
                lines.append(f"<h2 style='color:#1a3a7a;border-bottom:2px solid #1a3a7a;padding-bottom:5px;'>{text}</h2>")
            elif level <= 4:
                lines.append(f"<h4 style='color:#333;'>{text}</h4>")
        elif stripped.startswith("【"):
            lines.append(f"<p style='font-weight:bold;color:#1a3a7a;margin-top:12px;'>{stripped}</p>")
        elif stripped.startswith("▸") or stripped.startswith("•"):
            lines.append(f"<li style='margin-left:15px;'>{stripped[1:].strip()}</li>")
        elif stripped.startswith("1.") or stripped.startswith("2.") or stripped.startswith("3."):
            lines.append(f"<p style='margin-left:10px;'>{stripped}</p>")
        elif stripped.startswith("⚠"):
            lines.append(f"<p style='color:#c0392b;'>{stripped}</p>")
        elif stripped.startswith("📎"):
            lines.append(f"<p style='color:#888;font-size:12px;'>{stripped}</p>")
        elif stripped:
            lines.append(f"<p>{stripped}</p>")
    
    style = """
    <style>
        body { font-family: -apple-system, 'Microsoft YaHei', sans-serif; font-size: 14px; line-height: 1.7; color: #333; padding: 20px; }
        .footer { margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 12px; color: #999; }
    </style>
    """
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">{style}</head><body>
{"".join(lines)}
<div class="footer">本报告由狗蛋AI自动生成 | 数据来源：东方财富+腾讯财经<br>仅供参考，不构成投资建议</div>
</body></html>"""
    return html


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 email_report.py <subject> [options]")
        print("  管道:  echo '报告内容' | python3 email_report.py <subject>")
        print("  参数:  python3 email_report.py <subject> --body '报告内容'")
        print("  附件:  python3 email_report.py <subject> --body '内容' /path/to/attach")
        sys.exit(1)
    
    subject = sys.argv[1]
    
    # 解析 --body 参数
    body = None
    attachments = []
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--body" and i + 1 < len(sys.argv):
            body = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--html" and i + 1 < len(sys.argv):
            # 直接使用html文件
            html_path = sys.argv[i + 1]
            if os.path.exists(html_path):
                html_file = f"file://{html_path}"
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                # 附加PDF或HTML附件
                attachments.append(html_path)
                # html内容作为body
                html_msg = MIMEMultipart('alternative')
                msg = MIMEMultipart('alternative')
                msg['From'] = FROM_EMAIL
                msg['To'] = TO_EMAIL
                msg['Subject'] = Header(subject, 'utf-8')
                
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)
                
                i += 2
                continue
            i += 2
        else:
            attachments.append(sys.argv[i])
            i += 1
    
    # 如果没有 --body，从 stdin 读取
    if body is None:
        body = sys.stdin.read()
    
    html = build_email(subject, body.split("\n"))
    send_email(subject, html, attachments)
    print(f"✅ 邮件已发送: {subject}")
