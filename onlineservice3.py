#!/usr/bin/env python2.7
# encoding: utf8
import os
import json
import time
import smtplib

import mechanize
from BeautifulSoup import BeautifulSoup

import config

_cache = False # debug

def get_infopage():
  if _cache:
    return open("cache.txt").read()
  else:
    qis_url = "https://qis2.hs-karlsruhe.de"
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

  exams = {}
  for tr in grade_tbl.findAll("tr"):
    texts = [td.text.strip() for td in tr.findAll("td")]
    if texts:
      exams[texts[0]] = {
        "name": texts[1],
        "sem": texts[2],
        "date": texts[3],
        "grade": texts[4],
        "status": texts[5],
        "comment": texts[6],
        "tries": texts[7] }
  return exams

def print_diff(examinfo, diff):
  for e in diff:
    print("%s: %s" % (examinfo[e]['name'], examinfo[e]['grade']))

def examresult(exam):
  return ("Note " + exam['grade']) if exam['grade'] else exam['status']

def get_maildata(exam):
  return (u'\r\n'.join((
      u"from: " + config.mail_sender,
      u"subject: %s in %s" % (examresult(exam), exam['name']),
      u"to: " + config.mail_recipient,
      u"mime-version: 1.0",
      u"content-type: text/html",
      u"",
      u"",
      u"Klausurergebnis für \"%s\": <b>%s</b>" % (
        exam['name'], examresult(exam))))).encode("utf8")

def send_email(examinfo, diff):
  session = smtplib.SMTP(config.smtp_server)
  session.starttls()
  session.login(config.smtp_username, config.smtp_password)
  for e in diff:
    session.sendmail(
        config.mail_sender,
        config.mail_recipient,
        get_maildata(examinfo[e]))
  session.quit()

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

def poll_and_notifiy():
  examinfo_old = load_examinfo()
  examinfo_new = poll_examinfo()
  save_examinfo(examinfo_new)
  if examinfo_old:
    diff = set(examinfo_new) - set(examinfo_old)
    if diff:
      print_diff(examinfo_new, diff)
      send_email(examinfo_new, diff)
    print "%s: %d updates" % (time.asctime(), len(diff))
  else:
    print "%s: init with %d exams" % (time.asctime(), len(examinfo_new))

if __name__=="__main__":
  while True:
    poll_and_notifiy()
    time.sleep(config.poll_interval)
