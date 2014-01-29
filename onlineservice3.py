#!/usr/bin/env python2.7
# encoding: utf8
import os
import json
import time
import smtplib
import traceback

from urllib2 import HTTPError

from email.MIMEText import MIMEText
from email.Header import Header
from email.Utils import parseaddr, formataddr

import mechanize
from BeautifulSoup import BeautifulSoup

try:
  import config
except ImportError:
  raise Exception("Error importing config.py - see config.py.default")

_cache = False # debug

qis_url = "https://qis2.hs-karlsruhe.de"
os3_url = "http://www.github.com/OttoAllmendinger/onlineservice3"

def get_infopage():
  if _cache:
    return open("cache.txt").read()
  else:
    browser = mechanize.Browser()
    browser.set_handle_robots(False)
    browser.open(qis_url)
    browser.select_form("loginform")
    browser['asdf'] = config.qis_username
    browser['fdsa'] = config.qis_password
    browser.submit()
    browser.follow_link(text_regex=r"Prüfungsverwaltung")
    browser.follow_link(text_regex=r"Notenspiegel")
    r = browser.follow_link(text_regex=r"Leistungen.*")
    data = r.read()
    open("cache.txt", "w").write(data)
    return data

def poll_examinfo():
  soup = BeautifulSoup(get_infopage())
  grade_tbl = None
  for tbl in soup.findAll("table"):
    if any(th.text=="Note" for th in tbl.findAll("th")):
      grade_tbl = tbl

  if grade_tbl==None:
    return {}

  exams = {}
  for tr in grade_tbl.findAll("tr"):
    texts = [td.text.strip() for td in tr.findAll("td")]
    if texts:
      info = {
        "name": texts[1],
        "sem": texts[2],
        "date": texts[3],
        "grade": texts[4],
        "status": texts[5],
        "comment": texts[6],
        "tries": texts[7] }
      key = str(hash((info['name'], info['date'], info['sem'], info['grade'])))
      exams[key] = info

  return exams

def print_diff(examinfo, diff):
  for e in diff:
    print("%s: %s" % (examinfo[e]['name'], examinfo[e]['grade']))

def examresult(exam):
  if exam['grade'].strip():
    return "Note " + exam['grade']
  else:
    return exam['status']

def get_maildata(sender, recipient, subject, body):
    # for python<2.7
    # source: http://mg.pov.lt/blog/unicode-emails-in-python
    sender_name, sender_addr = parseaddr(sender)
    recipient_name, recipient_addr = parseaddr(recipient)
    sender_name = str(Header(unicode(sender_name), 'utf8'))
    recipient_name = str(Header(unicode(recipient_name), 'utf8'))
    sender_addr = sender_addr.encode('ascii')
    recipient_addr = recipient_addr.encode('ascii')
    msg = MIMEText(body.encode('utf8'), 'html', 'utf8')
    msg['From'] = formataddr((sender_name, sender_addr))
    msg['To'] = formataddr((recipient_name, recipient_addr))
    msg['Subject'] = Header(unicode(subject), 'utf8')
    return msg.as_string()

def send_emails(mail_data_list):
  session = smtplib.SMTP(config.smtp_server)
  session.starttls()
  session.login(config.smtp_username, config.smtp_password)
  for data in mail_data_list:
    session.sendmail(config.mail_sender, config.mail_recipient, data)
  session.quit()

def send_email(mail_data):
  send_emails([mail_data])

def send_examinfo_email(examinfo, diff):
  mail_data_list = []
  for e in (examinfo[d] for d in diff):
    e['result'] = examresult(e)
    data = get_maildata(
        config.mail_sender,
        config.mail_recipient,
        u"%(result)s in %(name)s" % e,
        (u"Klausurergebnis für %(name)s: <b>%(result)s<b>" % e) +
        ("<br><br><a href=\"%s\">HSKA Online-Service 2</a>" % qis_url))
    mail_data_list.append(data)
  send_emails(mail_data_list)

def send_exception_email(exception_with_traceback, error_count, fatal):
  send_email(get_maildata(
        config.mail_sender,
        config.mail_recipient,
        u"Fehler bei onlineservice3",
        (u"Fehler bei onlineservice3 (error_count=" + error_count + u")"
          u"<hr><pre>\n"
            + (u"%s" % exception_with_traceback)
            + u"\n\n</pre><hr>"
            + (u"Dienst wird beendet." if fatal else u""))))

def load_examinfo():
  if not os.path.exists(config.examinfo_path):
    return {}
  f = open(config.examinfo_path)
  data = json.load(f)
  f.close()
  return data

def save_examinfo(examinfo):
  f = open(config.examinfo_path, 'w')
  json.dump(examinfo, f, indent=2)
  f.close()

def log(msg):
  print "%s: %s" % (time.asctime(), msg)

def poll_and_notifiy(skip_mail):
  examinfo_old = load_examinfo()
  examinfo_new = poll_examinfo()
  if examinfo_old:
    diff = set(examinfo_new) - set(examinfo_old)
    if diff:
      print_diff(examinfo_new, diff)
      if not skip_mail:
        send_examinfo_email(examinfo_new, diff)
    log("%d updates" % len(diff))
  else:
    log("init with %d exams" % len(examinfo_new))
  save_examinfo(examinfo_new)

if __name__=="__main__":
  import sys

  skip_mail = '--nomail' in sys.argv

  error_count = 0
  max_errors = 3

  while True:
    try:
      poll_and_notifiy(skip_mail)
      error_count = 0
    except HTTPError, e:
      if e.code == 503:
        # happens between ~ 0:30 and 1:00
        log("HTTP Reply 503: Online-Service 2 beauty sleep")
      elif e.code == 502:
        # happens every once in a while
        log("HTTP Reply 502: Online-Service 2 expected failure")
    except Exception, e:
      error_count += 1
      fatal = (error_count == max_errors)

      log("Unexpected failure. Please report on %s "
          "and include cache.txt" % os3_url)
      traceback.print_exc()

      try:
        send_exception_email(traceback.format_exc(), error_count, fatal)
      except Exception, e:
        print("Failed to send exception email")
        traceback.print_exc()


      if fatal:
        raise

    time.sleep(config.poll_interval)

