# -*- coding: utf-8 -*-
import json
import os
import re
import urllib.request
from urllib import parse
import time

# 쓰레드, 큐를 위한 라이브러리 추가
import multiprocessing as mp
from threading import Thread

from bs4 import BeautifulSoup
from slackclient import SlackClient
from flask import Flask, request, make_response, render_template
from selenium import webdriver
from operator import itemgetter
from requests.sessions import Session

app = Flask(__name__)

generations = ['전체 연령대', '10대', '20대', '30대', '40대', '50대']

slack_token = 'xoxb-504131970294-508555503175-x5Bktl8WiLzgv6zEA1poXrAW'
slack_client_id = '504131970294.508554740327'
slack_client_secret = '3705c43a70f9a52a0fe70e34f3bef9b6'
slack_verification = '3WKgs4HaxxPmADHSDeLUFfXv'
sc = SlackClient(slack_token)
global_words = []
client_msg_id_history = []

def urlRequest(url_str):
     with urllib.request.urlopen(url_str) as site:
        return site.read()

def parseHtml(site):
    return BeautifulSoup(site, 'html.parser')

def navKeywordsURL(parsed_html):
    soup = parsed_html.find('div', class_=re.compile('area_hotkeyword.*'))
    url = soup.find('a', class_='ah_ha', href=re.compile('https?://datalab.naver.com/.*'))
    return url['href']

def navKeywordsCrawling(site, type):
    soup = parseHtml(site)
    keywords = []
    list = None
    for ranking in soup.find_all('div', class_='keyword_rank'):
        ages = ranking.find('strong', class_='rank_title v2').get_text()
        if ages == type:
            list = ranking
            break
    if list:
        for word_list in list.find_all('li', class_='list'):
            keywords.append(word_list.find('span', class_='title').get_text())
    return keywords, type

def youtubeCrawling(query_word):
    list_href = []
    url = "https://www.youtube.com/results?search_query=" + parse.quote(query_word)
    req = urllib.request.Request(url)
    sourcecode = urllib.request.urlopen(url).read()
    soup = BeautifulSoup(sourcecode, "html.parser")
    for i, keyword in enumerate(soup.find_all("div", class_="yt-lockup-content")):
       #print(keyword)
       if i < 10:
           try:
               if 'list' in keyword.find("a", class_="yt-uix-tile-link yt-ui-ellipsis yt-ui-ellipsis-2 yt-uix-sessionlink spf-link ").get("href"):
                   continue
               list_href.append(["https://www.youtube.com" + keyword.find("a", class_="yt-uix-tile-link yt-ui-ellipsis yt-ui-ellipsis-2 yt-uix-sessionlink spf-link ").get("href")])
               list_href[-1].append(keyword.find("span").get_text())
               list_href[-1].append(keyword.find("a", class_="yt-uix-sessionlink spf-link ").get_text())
               list_href[-1].append(keyword.find("span", class_="accessible-description").get_text().split('길이: ')[1])
               list_href[-1].append(keyword.find("ul", class_="yt-lockup-meta-info").get_text().split()[0])
               list_href[-1].append(keyword.find("ul", class_="yt-lockup-meta-info").get_text().split()[2][:-1])
           except:
               pass
    for i in range(0, len(list_href)):
        url = str(list_href[i][0])
        req = urllib.request.Request(url)
        sourcecode = urllib.request.urlopen(url).read()
        soup = BeautifulSoup(sourcecode, "html.parser")
        try:
            keyword = str(soup.find_all("strong", class_="watch-time-text")).split(': ')[1]
            list_href[i].insert(3, keyword.split('<')[0])
        except:
            list_href[i].insert(3, '')

    list_href = sorted(list_href, key=get_freq, reverse=True)

    return list_href

def get_freq(list_href):
    list_href = list_href[-1].split(',')
    view = str()
    for i in range(0, len(list_href)):
        view = view + list_href[i]
    try:
        return int(view)
    except:
        return 0

def getKeywords(type):
    driver = webdriver.Chrome('C:\\Users\\student\\Desktop\\chromedriver_win32\\chromedriver')
    driver.implicitly_wait(2)
    driver.get('https://datalab.naver.com/keyword/realtimeList.naver?where=main')
    html = driver.page_source
    keywords, type = navKeywordsCrawling(html, type)
    driver.quit()
    return keywords[:10]

# threading function
def processing_event(queue):
   while True:
       global client_msg_id_history
       # 큐가 비어있지 않은 경우 로직 실행
       if not queue.empty():
           if len(client_msg_id_history) > 20:
               client_msg_id_history.clear()
           slack_event = queue.get()
           if 'client_msg_id' in slack_event['event']:
               msg_id = slack_event['event']['client_msg_id']
               if msg_id in client_msg_id_history:
                   pass
               else:
                   client_msg_id_history.append(msg_id)
                   # Your Processing Code Block gose to here
                   channel = slack_event["event"]["channel"]
                   text = slack_event["event"]["text"]
                   if text:
                       matching = re.search(r'(<\S+>) (.*)', text)
                       # 챗봇 크롤링 프로세스 로직 함수
                       if matching:
                           attachments_list = processing_function(matching.group(2))
                           sc.api_call("chat.postMessage",
                           channel= slack_event["event"]["channel"],
                           text='',
                           attachments=attachments_list
                           )
                       else:
                           sc.api_call("chat.postMessage",
                           channel= slack_event["event"]["channel"],
                           text='저는 연령대별로 급상승 검색어를 찾아드리고, 검색어에 따른 유튜브 동영상을 검색해드려요!\n알고싶은 연령대를 저를 태그해서 입력해주세요. e.g. @TAG 10대'
                           )

# 크롤링 함수
def processing_function(text_msg):
    global global_words
    attachments_list = []
    # 함수를 구현해 주세요
    if text_msg in generations:
        global_words = getKeywords(text_msg)
        global_words.append('위 키워드 중 하나를 입력해주세요.')
        msg_options = {
            'color': '#36a64f',
            'pretext' : '{}가 많이 검색하는 top 10 키워드입니다'.format(text_msg),
            'author_name' : 'SSAFY_GUMI_3_YOUTUVER',
            'title' : '키워드 목록',
            'text' : "\n".join(global_words),
            'footer' : 'Youtuver',
            'footer_icon': 'https://platform.slack-edge.com/img/default_application_icon.png'
        }
        attachments_list.append(msg_options)
    else:
        if not global_words:
            msg_options = {
                'color': '#ff2400',
                'text' : '연령대를 입력해주세요. 50대까지 가능해요! e.g. 전체 연령대, 10대, 20대',
                'footer' : 'Youtuver',
                'footer_icon': 'https://platform.slack-edge.com/img/default_application_icon.png'
            }
            attachments_list.append(msg_options)
        elif text_msg in global_words:
            youtubeList = youtubeCrawling(text_msg)
            '''msg_options = {
                'color': '#36a64f',
                'pretext' : '{}에 대해 검색한 결과입니다'.format(word),
                'author_name' : 'SSAFY_GUMI_3_YOUTUVER',
                'title' : '유튜브 동영상 목록',
                'title_link' : youtubeList[0][0],
                'text' : '마하반야 바라밀다',
                'footer' : 'Youtuver',
                'footer_icon': 'https://platform.slack-edge.com/img/default_application_icon.png'
            }
            '''
            for youtubeEntity in youtubeList:
                try:
                    msg_options = {
                        'color' : '#36a64f',
                        'title' : youtubeEntity[1],
                        'title_link' : youtubeEntity[0],
                        'author_name' : youtubeEntity[2] if youtubeEntity[2].find('재생목록') == -1 else '',
                        'text' : '업로드 날짜 : {} , 영상길이 : {} 조회수 : {}'.format(youtubeEntity[3], youtubeEntity[4], youtubeEntity[6])
                    }
                    attachments_list.append(msg_options)
                except:
                    pass
        else:
            msg_options = {
                'color': '#ff2400',
                'text' : '유효하지 않은 키워드입니다. 다시 검색해주세요',
                'footer' : 'Youtuver',
                'footer_icon': 'https://platform.slack-edge.com/img/default_application_icon.png'
            }
            attachments_list.append(msg_options)

    return attachments_list


# 이벤트 핸들하는 함수
def _event_handler(event_type, slack_event):
   if event_type == "app_mention":
       event_queue.put(slack_event)
       return make_response("App mention message has been sent", 200, )


@app.route("/slackbot", methods=["GET", "POST"])
def hears():
   slack_event = json.loads(request.data)

   if "challenge" in slack_event:
       return make_response(slack_event["challenge"], 200, {"content_type":
                                                                "application/json"
                                                            })

   if slack_verification != slack_event.get("token"):
       message = "Invalid Slack verification token: %s" % (slack_event["token"])
       make_response(message, 403, {"X-Slack-No-Retry": 1})

   if "event" in slack_event:
       event_type = slack_event["event"]["type"]
       return _event_handler(event_type, slack_event)

   # If our bot hears things that are not events we've subscribed to,
   # send a quirky but helpful error response
   return make_response("[NO EVENT IN SLACK REQUEST] These are not the droids\
                        you're looking for.", 404, {"X-Slack-No-Retry": 1})


@app.route("/", methods=["GET"])
def index():
   return "<h1>Server is ready.</h1>"


if __name__ == '__main__':
   event_queue = mp.Queue()

   p = Thread(target=processing_event, args=(event_queue,))
   p.start()
   print("subprocess started")

   app.run('0.0.0.0', port=8080)
   p.join()
