"""
Groupme bot running on Heroku.
"""

# Copyright (C) 2016 Alexander Tomlinson
# Distributed under the terms of the GNU General Public License (GPL).

from __future__ import print_function

from groupy import Bot, Group, config, attachments
from flask import Flask, request
from safygiphy import Giphy
import logging
import signal
import requests
from string import punctuation

# google cal search import
from oauth2client.service_account import ServiceAccountCredentials
from httplib2 import Http
from apiclient import discovery

# forecast api
from forecastio import load_forecast as forecast
from geopy.geocoders import Nominatim

from bs4 import BeautifulSoup as bs
from random import randint
import urllib.parse as urlparse
import dateutil.parser
import markovify
import datetime
import psycopg2
import random
import json
import sys
import os
import re
import io

# API keys are stored as environment variables in Heroku

# REQUIRED API KEYS
# GroupMe: GROUPY_KEY
# Postgres: DATABASE_URL (provided by Heroku)
# Port: PORT (provided by Heroku)

# OPTIONAL API KEYS
# Google search: CUSTOM_SEARCH_ID
# Google search: CUSTOM_SEARCH_KEY
# Dark Sky (forecast.io): FORECAST_KEY
# Google calendar id and key (not env var, in calendar code)

HAVE_GOOGLE_KEY = True
HAVE_FORECAST_KEY = True
HAVE_CALENDAR_KEY = True


class GroupMeBot(object):
    """
    Simple Groupme bot
    """
    def __init__(self, bots):
        self.bots = bots

        self.cal_service = self.setup_calservice()
        self.markovs = None
        # self.setup_markovs()

        log.info('Ripbot up and ready.')

        if os.environ.get('IS_TEST', False):
            # post to test
            self.post(23373961, 'Updated')

    def callback(self):
        """
        Method to send responses on callbacks.
        """
        # decode json callback to dictionary
        data = json.loads(request.data.decode('utf8'))

        self.parse_and_post(data)

        return 'OK'

    def parse_and_post(self, data):
        """
        Parses callback JSON data and selects appropriate response.
        :param data: data from groupme server
        """

        name = None
        text = None
        system = None
        group_id = None
        bot_name = None

        if 'name' in data:
            name = data['name']

        if 'text' in data:
            text = data['text'].strip()

        if 'system' in data:
            system = data['system']

        if 'group_id' in data:
            try:
                group_id = int(data['group_id'])
                bot_name = self.bots[group_id]['name']
            except KeyError:
                log.info('Missing group; restarting')
                # just make the app crash, screw it
                sys.exit(0)

        else:
            log.error('No group_id. Unknown originating group.')
            return

        post = None
        attachment = None

        # check if system message
        if system:
            log.info('BOT: Got system message, parsing...')

            if text is not None:
                new_user = re.match('(.*) added (.*) to the group', text)
                name_change = re.match('(.*) changed name to (.*)', text)

                if new_user is not None:
                    post = self.is_new_user(new_user, group_id)

                if name_change is not None:
                    post = self.is_name_change(name_change, group_id)

        # non system messages
        elif name is not None:

            log.info('BOT: Got message, parsing: "{}"'.format(text))

            if text is not None:

                # bot can gifme itself
                gifme = re.match(
                    '^(?:@)?(?:{})?(?: )?gif(?: )?(?:me)? (.*)'.format(bot_name),
                    text, re.IGNORECASE)

                if gifme is not None:
                    post = self.is_gifme(gifme, text)

                # not originating from ripbot
                if str(name) != str(bot_name):

                        # matches string in format: '@First Last ++ more text'
                        plus_minus = re.match(
                            '^(.*?)(\+\+|\-\-)(.*)', text)

                        imageme = re.match(
                            '^(?:@)?(?:{})?(?: )?image(?: )?(?:me)? (.*)'.format(bot_name),
                            text, re.IGNORECASE)

                        animateme = re.match(
                            '^(?:@)?(?:{})?(?: )?animate(?: )?(?:me)? (.*)'.format(bot_name),
                            text, re.IGNORECASE)

                        youtube = re.match(
                            '^(?:@)?(?:{})?(?: )?(?:youtube|yt)(?: )?(?:me)? (.*)'.format(bot_name),
                            text, re.IGNORECASE)

                        top_scores = re.match(
                            '^(?:@)?(?:{} )?topscores$'.format(bot_name),
                            text, re.IGNORECASE)

                        bottom_scores = re.match(
                            '^(?:@)?(?:{} )?bottomscores$'.format(bot_name),
                            text, re.IGNORECASE)

                        help = re.match(
                            '^(?:@)?(?:{} )?help$'.format(bot_name),
                            text, re.IGNORECASE)

                        who = re.match(
                            '^(?:@)?(?:{} )who'.format(bot_name),
                            text, re.IGNORECASE)

                        why = re.match(
                            '^(?:@)?(?:{} )why'.format(bot_name),
                            text, re.IGNORECASE)

                        when_where = re.match(
                            '^(?:@)?(?:{} )(?:when|where)(?: is|\'s)(?: the)?(?: next)? (.*)'.format(bot_name),
                            text, re.IGNORECASE)

                        agenda = re.match(
                            '^(?:@)?(?:{} )?agenda(?: )?(\d)?$'.format(bot_name),
                            text, re.IGNORECASE)

                        forecast = re.match(
                            # '^(?:@)?(?:{} )?forecast$'.format(bot_name),  # elections
                            r'^(?:@)?(?:{}\b)?(?: )?forecast\b(.*)?'.format(bot_name),  # weather
                            text, re.IGNORECASE)

                        markov = re.match(
                            r'^(?:@)?(?:{}\b)?(?: )?markov( \S+)?$'.format(bot_name),
                            text, re.IGNORECASE)

                        at_all = re.match(
                            r'^.*?\@all\b',
                            text, re.IGNORECASE)

                        at_leadership = re.match(
                            r'^.*?\@leadership\b',
                            text, re.IGNORECASE)

                        if plus_minus is not None:
                            post = self.is_plusminus(plus_minus, text, group_id, bot_name, name)

                        elif imageme is not None:
                            if HAVE_GOOGLE_KEY:
                                post = self.is_imageme(imageme, text)

                        elif animateme is not None:
                            if HAVE_GOOGLE_KEY:
                                post = self.is_imageme(animateme, text, True)

                        elif youtube is not None:
                            if HAVE_GOOGLE_KEY:
                                post = self.is_youtube(youtube, text)

                        elif top_scores is not None:
                            post = self.is_scores(text, group_id)

                        elif bottom_scores is not None:
                            post = self.is_scores(text, group_id, False)

                        elif help is not None:
                            post = self.is_help(text)

                        elif who is not None:
                            post = self.is_who(text, group_id)

                        elif why is not None:
                            post = self.is_why(text)

                        elif when_where is not None:
                            if HAVE_CALENDAR_KEY:
                                if str(bot_name) in ['test-ripbot', 'ripbot', 'krom']:
                                    post = self.is_when_where(when_where, text,
                                                              str(bot_name))

                        elif agenda is not None:
                            if HAVE_CALENDAR_KEY:
                                if str(bot_name) in ['test-ripbot', 'ripbot', 'krom']:
                                    post = self.is_agenda(agenda, text,
                                                          str(bot_name))

                        elif forecast is not None:
                            if HAVE_FORECAST_KEY:
                                post = self.is_forecast(forecast, text)

                        elif markov is not None:
                            post = self.is_markov(markov, text, group_id)

                        elif at_all is not None:
                            post, attachment = self.is_at_all(group_id)

                        elif at_leadership is not None:
                            post, attachment = self.is_at_leadership(group_id)

        if post is not None:
            self.post(group_id, post, attachment)

        else:
            log.info('No matches; ignoring.')

    def post(self, group_id, to_post, attachments=None):
        """
        Posts to proper group.

        :param group_id: group to post to
        :param to_post: string of post, or iterable of posts
        """
        post = self.bots[group_id]['post']

        if attachments is None:
            try:
                post(to_post)

            except (TypeError, AttributeError):
                log.info('Have multiple messages, posting all')
                for message in to_post:
                    post(message)

        else:
            log.info('Have attachments, posting with.')
            try:
                post(to_post, attachments)

            except (TypeError, AttributeError):
                log.info('Have multiple messages, posting all')
                for message, attachment in zip(to_post, attachments):
                    post(message, attachment)

    def is_plusminus(self, match, text, group_id, bot_name, name):
        """
        Response for adding/subtracting points
        :param match: re match groups
        :param text: message text
        :param group_id: group id
        :param name: name of whoever is assigning points
        """
        plus_or_minus = match.group(2)
        # split along punctuation characters
        ignore = re.sub("[-'@/]", '', punctuation)
        points_to = re.split(r'[{}]+'.format(re.escape(ignore)), match.group(1).strip())[-1].strip()

        # special case where name is "@@"
        if points_to.startswith('@@'):
            points_to = points_to[1:]
        else:
            points_to = points_to.lstrip('@')

        what_for = match.group(3).strip()
        what_for = re.sub(r"^(for|because|cause|cuz)", '', what_for).lstrip()
        what_for = what_for.rstrip('.!?')

        post_text = ''

        if type(points_to) == int or len(points_to) > 0:
            log.info('MATCH: plusminus to {} in "{}".'.format(points_to,
                                                              text))

            if group_id == 6577279 and points_to == 'Matt':
                plus_or_minus = '++'

            if points_to.lower() == str(bot_name).lower() and plus_or_minus == '--':
                log.info('Attempted to downvote bot. Not allowing.')
                post_text += 'Lol no. @'
                plus_or_minus = '--'
                points_to = str(name)
                what_for = 'not knowing who\'s boss'

            if plus_or_minus == '++':
                if points_to.lower() == 'chipotle':
                    points = db.sub_point(points_to, group_id)
                else:
                    points = db.add_point(points_to, group_id)

            elif plus_or_minus == '--':
                if points_to.lower() == 'baja fresh':
                    points = db.add_point(points_to, group_id)
                else:
                    points = db.sub_point(points_to, group_id)

            post_text += '{} now has {} point'

            if points != 1:
                post_text += 's'

            if what_for:
                post_text += ', most recently for {}.'
                post_text = post_text.format(points_to, points, what_for)
            else:
                post_text += '.'
                post_text = post_text.format(points_to, points)

            if points_to.lower() == 'core':
                if not points % 10 == 0:
                    return None

                if points == 500:
                    post_text += ' Congrats! You guys did it!'
            
            return post_text

    def is_gifme(self, match, text, sorry=False):
        """
        Response for querying a gif. Uses GiphyAPI.
        :param match: re match groups
        :param text: message text
        """
        if sorry:
            try:
                return gif(tag='sorry')['data']['image_url']
            except:
                return ''

        query = match.group(1).rstrip()
        sorry = None

        if len(query) > 0:
            log.info('MATCH: gifme in {}.'.format(text))

            try:
                post_text = gif(tag=query, rating='r')['data']['image_url']

            except (TypeError, IndexError):
                post_text = 'Sorry, no gifs matching those tags.'

                try:
                    sorry = gif(tag='sorry')['data']['image_url']

                except:
                    pass

            if sorry is not None:
                post_text = [post_text, sorry]

            return post_text

    def is_imageme(self, match, text, animated=False):
        """
        Response for querying an image. Uses google custom search.
        :param match: re match groups
        :param text: message text
        """
        query = match.group(1).rstrip()
        sorry = None

        if len(query) > 0:
            log.info('MATCH: imageme in {}.'.format(text))

            try:
                query = {
                    'q': query,
                    'searchType': 'image',
                    'safe': 'off',
                    'fields': 'items(link)',
                    'imgSize': 'large',
                    'cx': os.environ['CUSTOM_SEARCH_ID'],
                    'key': os.environ['CUSTOM_SEARCH_KEY']
                }

                if animated:
                    query['fileType'] = 'gif'
                    query['hq'] = 'animated'
                    query['tbs'] = 'itp:animated'

                r = requests.get('https://www.googleapis.com/customsearch/v1', params=query)
                post_text = random.choice(r.json()['items'])['link']

            except:
                post_text = 'Sorry, no images matching those tags.'

                try:
                    sorry = gif(tag='sorry')['data']['image_url']

                except:
                    pass

            if sorry is not None:
                post_text = [post_text, sorry]

            return post_text

    def is_youtube(self, match, text):
        """
        Response for querying an youtube video. Uses google custom search.
        :param match: re match groups
        :param text: message text
        """
        query = match.group(1).rstrip()
        sorry = None

        if len(query) > 0:
            log.info('MATCH: youtube in {}.'.format(text))

            try:
                query = {
                    'q': query,
                    'part': 'snippet',
                    'fields': 'items(id(videoId))',
                    'safeSearch': 'none',
                    'key': os.environ['CUSTOM_SEARCH_KEY']
                }

                r = requests.get('https://www.googleapis.com/youtube/v3/search', params=query)
                videoId = r.json()['items'][0]['id']['videoId']
                post_text = 'https://www.youtube.com/watch?v={}'.format(videoId)

            except (TypeError, IndexError):
                post_text = 'Sorry, no videos that search matching those tags.'

                try:
                    sorry = gif(tag='sorry')['data']['image_url']

                except:
                    pass

            if sorry is not None:
                post_text = [post_text, sorry]

            return post_text

    def is_scores(self, text, group_id, top=True):
        """
        Response for querying top or bottom scorers.

        :param text: message text
        :param top: bool, True if want top scores, False for bottom
        """
        log.info('MATCH: topscores in "{}".'.format(text))

        if top:
            top_scores = db.get_scores(group_id)
            post_text = '>Top 10 scores:\n'
        else:
            top_scores = db.get_scores(group_id, False)
            post_text = '>Top 10 golf scores:\n'

        for i, score in enumerate(top_scores):
            post_text += '\n{}. '.format(i+1)

            # capitalize if only 2 letters (as in AT, KP)
            # need better way to check this. Original entry in DB is
            # unreliable though so idk.
            if len(top_scores[i][0]) == 2:
                post_text += '{}'.format(top_scores[i][0].upper())
            else:
                post_text += '{}'.format(top_scores[i][0].lower().title())

            post_text += ' with {} point'.format(top_scores[i][1])
            if top_scores[i][1] != 1:
                post_text += 's'

        return post_text

    def is_help(self, text):
        """
        Response to asking for help. Returns list of commands.
        :param text:
        :return:
        """
        post_text = 'Possible commands (bracket denotes optional):'
        post_text += '\n[@]something ++|-- [reason]'
        post_text += '\n[[@]botname] gifme giphy search terms'
        post_text += '\n[[@]botname] imageme google images search terms'
        post_text += '\n[[@]botname] youtube|yt search terms'
        post_text += '\n[[@]botname] topscores|bottomscores'
        post_text += '\n[@]botname who|why question'
        post_text += '\n[@]botname when|where calendar query (need ' \
                     'associated calendar)'
        post_text += '\n[[@]botname] agenda [int]'
        post_text += '\n[[@]botname] forecast [location]'
        post_text += '\n[[@]botname] markov [single start word (case sensitive)]'
        post_text += '\n@all mention all users'

        return post_text

    def is_who(self, text, group_id):
        """
        Response for asking ripbot who.
        """
        log.info('MATCH: who in "{}".'.format(text))

        member = Group.list().filter(group_id=str(group_id))[0].members()

        intro = ['Signs Point to ',
                 'Looks like ',
                 'Winner is ',
                 'I think it was ']

        post_text = random.choice(intro) + random.choice(member).nickname

        return post_text

    def is_why(self, text):
        """
        Response for asking ripbot why.
        """
        log.info('MATCH: why in "{}".'.format(text))

        reasons = [
            'Because their dinner isn\'t ready',
            'Because someone flushed his poop before he could look at it',
            'Because they like Chipotle... and didn\'t even plus plus it',
            # 'Because their cat downloaded all of that child porn',
            'Because they\'re from Texas',
            'Because @AT made them do it'
        ]

        post_text = random.choice(reasons)

        return post_text

    ''' DEPRECATED NOW THAT ELECTION IS OVER
    def is_forecast(self, text):
        """
        Gets election forecast from 538. Scraping isn't very robust.

        :param text:
        :return:
        """
        log.info('MATCH: forecast in "{}".'.format(text))

        site = 'http://projects.fivethirtyeight.com/2016-election-forecast/'

        r = requests.get(site)
        soup = bs(r.text, 'html.parser')

        win_prob = soup.findAll('div', {'data-card': 'winprob-sentence',
                                        'class': 'card card-winprob card-winprob-us '
                                        'winprob-bar'})[0]

        heads = win_prob.findAll('div', {'class': 'candidates heads'})[0]

        forecast = {}

        for head in heads.contents:
            candidates = head.findAll('div', {'class': 'candidate-text'})

            for candidate in candidates:
                name = candidate.p.text
                odds = candidate.findAll('p', {'data-key': 'winprob'})[0].text
                odds = float(odds.rstrip('%'))

                forecast[name] = odds

        post_text = ''
        post_text += '>Election forecast per 538:\n'

        for k, v in forecast.items():
            post_text += '\n{}: {}%'.format(k, v)

        post_text += '\n\nsource: http://projects.fivethirtyeight.com/2016-election-forecast/'

        return '#toosoon'
    '''

    def is_forecast(self, match, text):
        """
        Gets forecast from DarkSky API.

        :param text:
        :return:
        """
        log.info('MATCH: forecast in "{}".'.format(text))

        query = match.group(1).strip()

        api_key = os.environ.get('FORECAST_KEY', None)

        if len(query) == 0:
            query = 'Portland, OR'
        elif 'election' in query:
            return '#toosoon'

        geo = Nominatim().geocode(query)
        if geo is None:
            return 'Sorry, location not found.'

        loc = (geo.latitude, geo.longitude)

        f = forecast(api_key, loc[0], loc[1], units='us')

        # summary of the days weather
        summary = f.hourly().summary
        summary = summary + ' '

        # specific details for the next hour
        temp = int(f.hourly().data[0].temperature)
        temp = str(temp) + ' °F, '

        rain = int(f.hourly().data[0].precipProbability * 100)
        rain = str(rain) + ' % chance of rain, '

        wind = f.hourly().data[0].windSpeed
        wind = str(wind) + ' mph wind for the next hour.'

        post_text = summary + temp + rain + wind

        return post_text

    def setup_calservice(self):
        """
        Sets up cal service.
        :return: cal service
        """
        scopes = ['https://www.googleapis.com/auth/calendar.readonly']

        keyfile = {
            "type": "service_account",
            "project_id": "groupemebot",
            # idk why its not working to get from env
            "private_key_id": "4abc03b0c291afedcb3e0c72add9cbc5f6e42fdf",
            # "private_key_id": str(os.environ['CAL_KEY_ID']),
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDDw8x3FHOi1s5J\n2veueLoEfrc1zABZ9kwj8+uUyNboBE6gdsSwxatnUnbf6hKe+qvCKtkGMheudHvn\nmD75G2nRpoYEn8YIjWo9AVJgkVSvrfNGtZcCFXzKlmCKt10uz1Dz4G4tDOEpD9sr\nesZhjJ+VL3ScDRuQ5ty3ZQUVQXJymzh2t8JZzzOQvzA/5ZxiPVfYL1hIyPxKcu+6\nLuUu6pDZKs8oHQwIMxTULMfqp2tvcif5WKrtpIrzX4ZC0BjMC+gFMkSFmJ10+KfL\n3IDqyFH1NK6mvjQ/huNBJi10p9AcSkgqUNocvE2avEWQ583aZ4oBpTv97xyemQtF\nzzQZmus5AgMBAAECggEBAKtcPiNSdLJq42JE2SARL4t1vDvMGdalwRqLjoDLmUq5\nUnYl4KB4N0SXK9VvGOOuuyCYzyYcPRyJfFhKrXzy4RsScCemD/w2hXNnL8u2C3JI\nizYvCENbucPABDwIq/mooc0IfIjUyFdgONKDgxmqtZoqUyGyW5noa/Xg6KUlh+AG\ntWQV0HF3GwtLHMhCYuwryMTRp5jGbBkfdexxV1Yx4CRlEOMw/6OFRAXtEc1Sgmyn\nYPSdQRuE6M2rdQUkBseTOrdLwQHs+SpgqbMA/rdvZP8fRSyN+0pC/uiXqXA0LYST\nSr4xdDh6XTdH2xQ41LDamNqGUyzjDxf7JW7YKn5Py4ECgYEA4aWTAuoW6MmceC/n\n90S1PfTRUkOlvW0RFwi8ww1+LNBIl9hWau1xqUU2M7886FnblW2fG8GF+RDJSkFC\nndO4Syi2U4+xS7WP7jlT2B58xxegdVnbzmCuNH+PerwUJem4oHMXZZZCNBMIjGp/\nVMNiCnpGnJ7zwEeF1d3ZCnt8qmkCgYEA3hkz+LKp7xk8ZVbqvbSnxrRcptQiioK0\nzdYZfumR4hXq7POwNwdW85VZPuu4sjP99hc52lE74e9reeTM82azsqmlMheVBqol\nY9O4B66h48q2/61JduTSBz6wDvBng57P5qzG39FAnFqs1gR/fIp0vrniX+ZmVM6o\n8Py2NF7BAFECgYA5TXX3AIGO3lw4/Vl4Jt+r+zcJIBq/7ymu4s4k7pFDSiWVQiA4\nCVKa/POV0pPiIaes2+jTAKNIK+YiUE5djD26AH3E3LHWmyYRBkfvk1Z2rN5XztkO\nIOk8dcR3E7o+Iot7W57ucmkfllHObuElInUMWh8CeS9HfiJTvIH4soFnOQKBgHYh\nXZ1IGk7MU21rX4vrjNmJkUZCyuR1RQm+eO0h+rAQDFZf/zgltT/2DfQDmMdgFBJS\npDjUwE8Z80ZwRfqog6fhx7XvCRr0YNLKB7Y+UmlApzkyyEJuzq9/zlED2WsOi3Ic\nL+NX/0+qgweKeOybECFp6Vgsyf0NtpoHMDqGs40hAoGAAgMnuMQMtaCJ3SUjDJt5\nhsSeJMNX+ZlcK10qp6frllYkr+YKC9TUdUj1M93OE0WMkTXmkkdDw5HQtHpEFtbo\nFkJv/oClJG7SVZG2EFkYoryDY9tRfR0l+72zf28Yo463Jl6o/s6Q7peuVsVI7OR4\ncytjkqN7RViEi72/axWIvi0=\n-----END PRIVATE KEY-----\n",
            # "private_key": str(os.environ['CAL_KEY']),
            "client_email": "ripbotcal@groupemebot.iam.gserviceaccount.com",
            "client_id": "114400750037198291116",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://accounts.google.com/o/oauth2/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/ripbotcal%40groupemebot.iam.gserviceaccount.com"
        }

        credentials = ServiceAccountCredentials.from_json_keyfile_dict(keyfile, scopes)

        http_auth = credentials.authorize(Http())

        service = discovery.build('calendar', 'v3', http=http_auth)

        return service

    def is_when_where(self, match, text, cal):
        """
        Response for asking ripbot when or where for calendar query.
        """

        log.info('MATCH: when_where in "{}".'.format(text))

        query = match.group(1).strip()
        query = query.rstrip('.!?')
        log.info('Querying calendar with "{}".'.format(query))

        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time

        calendars = {
            'rip' : '5d1j2fnq4irkl6q15va06f6e4g@group.calendar.google.com',
            'reed': 'reedmensultimate@gmail.com'
        }

        if cal in ['ripbot', 'test-ripbot']:
            calendar = calendars['rip']
        elif cal == 'krom':
            calendar = calendars['reed']

        try:
            event_result = self.cal_service.events().list(
                calendarId=calendar,
                timeMin=now,
                maxResults=1,
                singleEvents=True,
                q=query,
                fields='items(location, summary, start)',
                orderBy='startTime').execute()
        except:
            return 'Something went wrong'

        event = event_result.get('items', [])

        if not event:
            post_text = 'No upcoming event found.'

        else:
            event = event[0]

            where = 'TBD'

            what = event['summary']

            try:  # to handle all day events
                when = event['start']['dateTime']
                dt = dateutil.parser.parse(when)
                when = dt.strftime('%a. %b. %d at %I:%M %p')
            except KeyError:
                when = event['start']['date']
                dt = dateutil.parser.parse(when)
                when = dt.strftime('%a. %b. %d')

            if 'location' in event:
                where = event['location']

            post_text = '>'
            post_text += what
            post_text += '\nlocation: {}'.format(where)
            post_text += '\ntime: {}'.format(when)

        return post_text

    def is_agenda(self, match, text, cal):
        """
        Response for asking ripbot for agenda.
        """
        log.info('MATCH: agenda in "{}".'.format(text))

        if match.group(1) is not None:
            num = int(match.group(1).strip())
        else:
            num = 3

        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time

        calendars = {
            'rip' : '5d1j2fnq4irkl6q15va06f6e4g@group.calendar.google.com',
            'reed': 'reedmensultimate@gmail.com'
        }

        if cal in ['ripbot', 'test-ripbot']:
            calendar = calendars['rip']
        elif cal == 'krom':
            calendar = calendars['reed']

        try:
            events_result = self.cal_service.events().list(
                calendarId=calendar,
                timeMin=now,
                maxResults=num,
                singleEvents=True,
                fields='items(location, summary, start)',
                orderBy='startTime').execute()
        except:
            return 'Something went wrong.'

        events = events_result.get('items', [])

        if not events:
            post_text = 'No upcoming event found.'

        else:
            post_text = '>'

            for event in events:
                where = 'TBD'
                what = event['summary']

                try:
                    when = event['start']['dateTime']
                    dt = dateutil.parser.parse(when)
                    when = dt.strftime('%a. %b. %d at %I:%M %p')
                except KeyError:
                    when = event['start']['date']
                    dt = dateutil.parser.parse(when)
                    when = dt.strftime('%a. %b. %d')

                if 'location' in event:
                    where = event['location']

                post_text += what
                post_text += '\nlocation: {}'.format(where)
                post_text += '\ntime: {}\n\n'.format(when)

        return post_text

    def setup_markovs(self):
        """
        Creates dict of markov generators
        """
        group_ids = list(map(int, [bot.group_id for bot in Bot.list()]))

        # make dict of all messages for each group
        self.markovs = {}

        log.info('Generating markovs.')
        for group_id in group_ids:
            messages = Group.list().filter(group_id=str(group_id))[0].messages()
            while messages.iolder():
                pass

            corpus = io.StringIO()
            for m in messages:
                corpus.write(str(m.text).strip() + '\n\n')

            text_model = markovify.NewlineText(corpus.getvalue())
            self.markovs[group_id] = text_model

        log.info('Markovs generated.')

    def is_markov(self, match, text, group_id):
        """
        Generates a random markov chain from appropriate group.

        :param group_id:
        :return:
        """
        log.info('MATCH: markov in "{}".'.format(text))
        query = match.group(1)

        if self.markovs is None:
            self.post(group_id, 'Busy making markov generator, could take up to 1 min. I\'ll let you know.')
            self.setup_markovs()
            return 'Markovs ready.'

        if match.group(1) is not None:
            # try once, if fails then try capitalizing, else give up.
            try:
                try:
                    log.info('Making markov chain with start.')
                    query = query.strip()
                    post_text = self.markovs[group_id].make_sentence_with_start(
                        query)
                    if post_text is None:
                        raise KeyError
                    log.info('Chain made: {}'.format(post_text))

                except KeyError:
                    log.info('Failed, trying to capitalize.')
                    query = query.capitalize()
                    post_text = self.markovs[group_id].make_sentence_with_start(
                        query)
                    if post_text is None:
                        raise ValueError

            except ValueError:
                log.info('Failed at making chain, returning sorry.')

                post_text = 'Couldn\'t make chain, sorry.'
                sorry = self.is_gifme(None, None, True)

                post_text = [post_text, sorry]

        else:
            log.info('Making random markov chain.')
            post_text = self.markovs[group_id].make_short_sentence(140)
            log.info('Chain made: {}'.format(post_text))

        return post_text

    def is_at_all(self, group_id):
        """
        Notifies all members of a group using attachment abuse.

        :param group_id:
        :return:
        """
        log.info('MATCH: @all')
        post_text = '@all ^'

        group = Group.list().filter(group_id=str(group_id))[0]

        ids = list(map(lambda x: str(x.user_id), group.members()))
        loci = [[1, 4]] * len(ids)

        mentions = attachments.Mentions(ids, loci)
        mentions = mentions.as_dict()

        return post_text, mentions

    def is_at_leadership(self, group_id):
        """
        Notifies all members of a group using attachment abuse.

        :param group_id:
        :return:
        """
        # only do for rip and test group
        if group_id not in [13678029, 23373961]:
            return None, None

        log.info('MATCH: @leadership')
        post_text = '@leadership ^'

        ids = [19577557,  # Touches
               19837433,  # Austin
               19385984,  # Blaydong
               15663495,  # Peach
               9838840]   # KP ++ for shorter id keeping comments lined up

        ids = list(map(str, ids))
        loci = [[1, 11]] * len(ids)

        mentions = attachments.Mentions(ids, loci)
        mentions = mentions.as_dict()

        # self.bots[int(group_id)]['post'](post_text, mentions)
        # return None, None

        return post_text, mentions

    def is_new_user(self, match, group_id):
        """
        Response to new user. Welcomes them and adds them to db.

        :param match: re match groups
        """
        user_name = match.group(2)
        log.info('SYSTEM MATCH: new user detected.')

        member = Group.list().filter(group_id=str(group_id))[0].members(
            ).filter(nickname=user_name)[0]
        user_id = int(member.user_id)

        # check if user already in DB
        if not db.exists(user_id, group_id):
            db.add_player(user_id, user_name, group_id)

        points = db.get_player_points(user_id, group_id)
        post_text = 'Welcome {}. You have {} points.'.format(user_name, points)

        return post_text

    def is_name_change(self, match, group_id):
        """
        Changed name in DB on nickname change.
        :param match: re match groups
        """
        user_name = match.group(1).rstrip()
        new_name = match.group(2).rstrip()
        log.info('SYSTEM MATCH: nickname change detected.')

        try:
            member = Group.list().filter(group_id=str(group_id))[0].members(

            ).filter(
                nickname=new_name)[0]
            user_id = int(member.user_id)
            log.info('GROUPY: Converted name to ID')

            # check if user already in DB
            if not db.exists(user_id, group_id):
                log.warning('DB: user not found in DB but should have been. '
                            'Probably does not have any points yet.')
                return

        except IndexError:  # fallback to switching by name rather than user_id
            user_id = user_name
            log.warning('GROUPY: Could not find user_id, falling back to '
                        'name.')

        db.change_player_name(new_name, user_id, group_id)

        points = db.get_player_points(user_id, group_id)
        post_text = 'Don\'t worry {}, you still have your {} point(s).'.format(
            new_name, points)

        return post_text


class Database(object):
    """
    Database holding player scores and ids
    """
    def __init__(self, group_ids):
        """
        Connect to db and setup cursor.
        """
        self.con = None
        self.cur = None

        try:
            # get database url from heroku
            urlparse.uses_netloc.append('postgres')
            url = urlparse.urlparse(os.environ['DATABASE_URL'])

            # connect to db
            self.con = psycopg2.connect(database=url.path[1:],
                                        user=url.username,
                                        password=url.password,
                                        host=url.hostname,
                                        port=url.port
                                        )
            log.info('DB: Successfully connected to database')

            # set up cursor for actions
            self.cur = self.con.cursor()

            # check if tables exist, if not create
            for group_id in group_ids:
                sql = "SELECT EXISTS(SELECT 1 FROM information_schema.tables " \
                      "WHERE table_name='{}')".format(group_id)

                self.cur.execute(sql)
                table_exists = self.cur.fetchone()[0]

                if not table_exists:
                    log.warning('DB: {} table not found, creating...'.format(
                        str(group_id)))
                    self.set_up_table(group_id)

        except psycopg2.DatabaseError as e:
            if self.con:
                self.con.rollback()
            log.error(e)

    def set_up_table(self, group_id):
        """
        Sets up postgres table if none found.

        :return:
        """
        sql = "CREATE TABLE \"{}\" (" \
              "id INT PRIMARY KEY," \
              "name TEXT,"\
              "points INT"\
              ")".format(group_id)

        try:
            if self.con is not None:
                self.cur.execute(sql)
                log.info('DB: {} table created'.format(group_id))
                self.con.commit()

        except psycopg2.DatabaseError as e:
            if self.con:
                self.con.rollback()
            log.error(e)

    def add_player(self, id, name, group_id, points=0):
        """
        Adds new player to table.
        :param id: member id number
        :param name: groupme nickname
        :param points: points to start with
        """
        sql = "INSERT INTO \"{}\" VALUES({}, '{}', {})"

        if self.con is not None:
            try:
                name = name.replace('\"', '')
                self.cur.execute(sql.format(group_id, id, name, points))
                self.con.commit()
                log.info('DB: Added {} to table with id# {} and {} point('
                         's).'.format(name, id, points))

            except psycopg2.DatabaseError as e:
                log.error(e)

        else:
            log.error('Failed adding player: not connected to DB.')

    def get_player_points(self, id, group_id):
        """
        Gets player points by name or id.
        :param id: player name or id
        :return: players points as int
        """
        if type(id) == int:
            sql = "SELECT points FROM \"{}\" WHERE id={}"

        else:
            id = id.replace('\'', '').replace('\"', '')
            sql = "SELECT points FROM \"{}\" WHERE LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                self.cur.execute(sql.format(group_id, id))
                points = self.cur.fetchone()

                if points is not None:
                    points = points[0]
                    log.info('DB: Fetched points of {} who has {} point(s).'.
                             format(id, points))
                else:
                    points = 0
                    id_num = self.new_id(group_id, id)
                    self.add_player(id_num, str(id), group_id, points)

                return points

            except psycopg2.DatabaseError as e:
                log.error(e)

        else:
            log.error('Failed retrieving player points: not connected to DB.')

    def add_point(self, id, group_id):
        """
        Adds point to player by name or id.
        :param id: player name or id
        :return: players points as int
        """
        # see if points_to is a person, get groupme ID if so
        try:
            member = Group.list().filter(
                group_id=group_id)[0].members().filter(nickname=id)[0]

            id = int(member.user_id)
            log.info('GROUPY: Converted name to ID')

        except(TypeError, IndexError):
            pass

        if type(id) == int:
            sql = "UPDATE \"{}\" SET points = points + 1 WHERE id={}"

        else:
            id = id.replace('\'', '').replace('\"', '')
            sql = "UPDATE \"{}\" SET points = points + 1 WHERE LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                # get points first because this checks if exists or not
                cur_points = self.get_player_points(id, group_id)
                self.cur.execute(sql.format(group_id, id))
                self.con.commit()
                log.info('ADD: point to {}; now has {} point(s).'.format(id,
                                                                         cur_points+1))
                return cur_points+1

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)

        else:
            log.error('Failed adding points: not connected to DB.')

    def sub_point(self, id, group_id):
        """
        Adds point to player by name or id.
        :param id: player name or id
        :return: players points as int
        """
        # see if points_to is a person, get groupme ID if so
        try:
            member = Group.list().filter(
                group_id=group_id)[0].members().filter(nickname=id)[0]

            id = int(member.user_id)
            log.info('GROUPY: Converted name to ID')

        except(TypeError, IndexError):
            pass

        if type(id) == int:
            sql = "UPDATE \"{}\" SET points = points - 1 WHERE id={}"

        else:
            id = id.replace('\'', '').replace('\"', '')
            sql = "UPDATE \"{}\" SET points = points - 1 WHERE " \
                  "LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                # get points first because this checks if exists or not
                cur_points = self.get_player_points(id, group_id)
                self.cur.execute(sql.format(group_id, id))
                self.con.commit()
                log.info('SUB: point to {}; now has {} point(s).'.format(id,
                                                                         cur_points-1))
                return cur_points-1

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)

        else:
            log.error('Failed adding points: not connected to DB.')

    def get_scores(self, group_id, top=True):
        """
        Gets top 10 scorers
        """
        if top:
            sql = 'SELECT name, points FROM \"{}\" ORDER BY points DESC LIMIT 10'
        else:
            sql = 'SELECT name, points FROM \"{}\" ORDER BY points ASC LIMIT 10'

        log.info('DB: getting top/bottom scorers.')

        if self.con is not None:
            try:
                self.cur.execute(sql.format(group_id))
                top_scores = self.cur.fetchall()

                return top_scores

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)

    def change_player_name(self, new_name, id, group_id):
        """
        Changes the players name in the db
        :param new_name:
        :param id:
        """
        if type(id) == int:
            sql = "UPDATE \"{}\" SET name='{}' WHERE id={}"

        else:
            id = id.replace('\'', '').replace('\"', '')
            new_name = new_name.replace('\"', '')
            sql = "UPDATE \"{}\" SET name=\"{}\" WHERE LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                self.cur.execute(sql.format(group_id, new_name, id))
                self.con.commit()

                log.info('DB: {} name changed to {}'.format(id, new_name))

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)

        else:
            log.error('Failed changing name: not connected to DB.')

    def new_id(self, group_id, id=None):
        """
        Generates new IDs for non players that need points
        :return: new random int
        """
        if id is not None:
            try:
                member = Group.list().filter(group_id=str(group_id))[
                    0].members().filter(
                    nickname=id)[0]
                id = int(member.user_id)
                log.info('ID: Got ID from Groupme. #{}'.format(id))

            except IndexError:
                id = None

        not_taken = False

        sql = "SELECT * FROM \"{}\" WHERE id={}"

        if id is None:
            while not not_taken:
                try:
                    id = randint(9999999, 100000000)
                    self.cur.execute(sql.format(group_id, id))
                    ret = self.cur.fetchone()
                    if ret is None:
                        not_taken = True

                except psycopg2.DatabaseError as e:
                    log.error(e)
                    break

        if not_taken:
            log.info('ID: Got ID from random. #{}'.format(id))

        return id

    def exists(self, id, group_id):
        """
        Checks if user id already in table.
        :param id: user id #
        :return: boolean
        """
        sql = 'SELECT * FROM \"{}\" WHERE id={}'

        try:
            # log.info('MESSAGE: ' + repr(id))
            self.cur.execute(sql.format(group_id, id))
            ret = self.cur.fetchone()

            if ret is None:
                return False
            else:
                return True

        except psycopg2.DatabaseError as e:
            log.error(e)


class RipbotServer(object):
    """
    Simple server for the ripbot.
    """
    def __init__(self):
        """
        Set server up.
        """
        # start flask and set up logging
        self.app = Flask(__name__)
        self.log = self.app.logger
        self.log.addHandler(logging.StreamHandler(sys.stdout))
        self.log.setLevel(logging.INFO)

        # sigterm handler
        signal.signal(signal.SIGTERM, self.shutdown)

    def setup(self):
        """
        Sets up callbacks.
        """
        # send callbacks to ripbot
        port = int(os.environ.get('PORT', 5000))
        self.app.route('/groupme', methods=['POST'])(bot.callback)
        self.app.run('0.0.0.0', port=port)

    def shutdown(self, signun, frame):
        """
        Gracefully shuts down flask server and ripbot.
        :param signun: param from signal callback
        :param frame: param from signal callback
        """
        self.log.info('SIGTERM: shutting down')
        sys.exit(0)


def start():
    # get groupme API key
    groupy_key = os.environ['GROUPY_KEY']
    config.API_KEY = groupy_key

    group_ids = [int(i.group_id) for i in Bot.list()]
    posts = [i.post for i in Bot.list()]
    names = Bot.list()

    # nested dict of group_id, with post method and bot name
    # eg: {23373961: {'post': <post method>, 'name': 'ripbot'}}
    bots = dict(zip(group_ids, [dict(zip(['post', 'name'], i)) for i in zip(
        posts, names)]))

    # start server
    server = RipbotServer()
    # GLOBALS ARE BAD
    # TODO: make a class to handle startup and restarting
    global log
    log = server.log

    # initialize bot
    # ripbot = GroupMeBot(bot.post)
    global bot
    bot = GroupMeBot(bots)

    # initialize database class
    global db
    db = Database(group_ids)

    # initialize giphy
    giphy = Giphy()
    global gif
    gif = giphy.random

    # init callbacks
    server.setup()

if __name__ == '__main__':
    start()
