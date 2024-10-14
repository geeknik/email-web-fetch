import smtplib
import email
import imaplib
import subprocess
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import parseaddr
from email import encoders
import re
import ssl

# Email configuration
IMAP_SERVER = 'imap.example.com'
SMTP_SERVER = 'smtp.example.com'
EMAIL_ACCOUNT = 'your_daemon@example.com'
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')  # Use environment variable for password

# Create SSL context for secure SMTP connection
SSL_CONTEXT = ssl.create_default_context()

# Set up email fetching from IMAP
def fetch_email():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select('inbox')

        status, response = mail.search(None, 'UNSEEN')
        email_ids = response[0].split()

        for e_id in email_ids:
            status, data = mail.fetch(e_id, '(RFC822)')
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Process the email and extract URL
            subject = msg['subject']
            if subject and subject.startswith('FETCH: '):
                parts = subject.split(' ')
                url = parts[1].strip()
                screenshot_flag = len(parts) > 2 and parts[2].lower() == 'screenshot'
                if is_valid_url(url):
                    recipient = parseaddr(msg['from'])[1]
                    fetch_and_send(url, recipient, screenshot_flag)
                else:
                    print(f"Invalid URL received: {url}")

        mail.logout()
    except Exception as e:
        print(f"Failed to fetch emails: {e}")

# Function to validate URL
def is_valid_url(url):
    url_regex = re.compile(
        r'^(https?://)'  # Only allow http:// or https://
        r'([\da-z\.-]+)\.([a-z\.]{2,6})'  # domain name
        r'([/\w \.-]*)*/?$'  # resource path
    )
    return re.match(url_regex, url) is not None

# Function to fetch webpage and send back to requester
def fetch_and_send(url, recipient, screenshot_flag):
    try:
        # Use wget to fetch the webpage
        result = subprocess.run(['wget', '-qO-', url], capture_output=True, text=True, timeout=30)
        page_content = result.stdout

        # Check if the content is too large
        if len(page_content) > 50000:  # Limit content size to 50KB
            page_content = "The fetched content is too large to be sent via email. Please provide a simpler page."

        # Create email with the page content
        msg = MIMEMultipart()
        msg['Subject'] = f'Result for {url}'
        msg['From'] = EMAIL_ACCOUNT
        msg['To'] = recipient

        text_part = MIMEText(page_content, 'plain')
        msg.attach(text_part)

        # Optionally take a screenshot of the webpage
        if screenshot_flag:
            screenshot_filename = 'screenshot.png'
            try:
                subprocess.run(['webkit2png', '-o', screenshot_filename, url], check=True, timeout=30)
                with open(screenshot_filename, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename={screenshot_filename}')
                    msg.attach(part)
                os.remove(screenshot_filename)
            except Exception as e:
                print(f"Failed to take screenshot: {e}")
                send_error_email(recipient, url, f"Failed to take screenshot: {e}")

        # Send the email
        with smtplib.SMTP(SMTP_SERVER, 587) as server:
            server.starttls(context=SSL_CONTEXT)
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ACCOUNT, [recipient], msg.as_string())

    except subprocess.TimeoutExpired:
        print(f"Fetching the URL timed out: {url}")
        send_error_email(recipient, url, "Fetching the URL timed out.")
    except Exception as e:
        print(f"Failed to fetch or send email: {e}")
        send_error_email(recipient, url, f"Failed to fetch the URL: {e}")

# Function to send an error email to the recipient
def send_error_email(recipient, url, error_message):
    msg = MIMEText(f"Error while fetching the URL '{url}': {error_message}")
    msg['Subject'] = f'Error fetching {url}'
    msg['From'] = EMAIL_ACCOUNT
    msg['To'] = recipient

    try:
        with smtplib.SMTP(SMTP_SERVER, 587) as server:
            server.starttls(context=SSL_CONTEXT)
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ACCOUNT, [recipient], msg.as_string())
    except Exception as e:
        print(f"Failed to send error email: {e}")

if __name__ == "__main__":
    fetch_email()
