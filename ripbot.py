"""
Groupme bot running on Heroku.
"""

# Copyright (C) 2016 Alexander Tomlinson
# Distributed under the terms of the GNU General Public License (GPL).

from __future__ import print_function

from groupy import Bot, Group, config
from flask import Flask, request
from safygiphy import Giphy
import logging
import signal

from random import randint
import urllib.parse as urlparse
import psycopg2
import json
import sys
import os
import re


class GroupMeBot(object):
    """
    Simple Groupme bot
    """
    def __init__(self, post):
        self.post = post
        log.info('Ripbot up and running.')

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

        if 'name' in data:
            name = data['name']

        if 'text' in data:
            text = data['text']

        if 'system' in data:
            system = data['system']

        # check if system message
        if system:
            log.info('BOT: Got system message, parsing...')

            if text is not None:
                new_user = re.match('(.*) added (.*) to the group', text)
                name_change = re.match('(.*) changed name to (.*)', text)

                if new_user is not None:
                    self.is_new_user(new_user)

                elif name_change is not None:
                    self.is_name_change(name_change)

                else:
                    log.info('No matches; ignoring.')

        # non system messages not originating from ripbot
        elif name is not None and name != which_bot:
            log.info('BOT: Got user message, parsing...')

            if text is not None:
                # matches string in format: '@First Last ++ more text'
                plus_minus = re.match('^(.*?)(\+\+|\-\-)(.*)', text)
                gifme = re.match('^(?:@)?(?:ripbot)?(?: )?gifme (.*)', text,
                                 re.IGNORECASE)
                top_scores = re.match('^(?:@)?(?:ripbot) topscores',
                                      text, re.IGNORECASE)
                bottom_scores = re.match('^(?:@)?(?:ripbot) bottomscores',
                                      text, re.IGNORECASE)

                if plus_minus is not None:
                    self.is_plusminus(plus_minus, text)

                if gifme is not None:
                    self.is_gifme(gifme, text)

                if top_scores is not None:
                    self.is_top_scores(text)

                if bottom_scores is not None:
                    self.is_top_scores(text, False)

                else:
                    log.info('No matches; ignoring.')

    def is_plusminus(self, match, text):
        """
        Response for adding/subtracting points
        :param match: re match groups
        :param text: message text
        """
        plus_or_minus = match.group(2)
        points_to = match.group(1).rstrip()
        points_to = points_to.lstrip()
        points_to = points_to.lstrip('@')

        what_for = match.group(3).lstrip().rstrip()
        what_for = re.sub(r"^(for|because)", '', what_for).lstrip()
        what_for = what_for.rstrip('.!?')

        if len(points_to) > 0:
            log.info('MATCH: plusminus to {} in "{}".'.format(points_to,
                                                              text))

            if plus_or_minus == '++':
                if points_to.to_lower == 'chipotle'
                    points = rip_db.sub_point(points_to)
                else
                    points = rip_db.add_point(points_to)
            elif plus_or_minus == '--':
                points = rip_db.sub_point(points_to)

            post_text = '{} now has {} point'

            if points != 1:
                post_text += 's'

            if what_for:
                post_text += ', most recently for {}.'
                post_text = post_text.format(points_to, points, what_for)
            else:
                post_text += '.'
                post_text = post_text.format(points_to, points)

            self.post(post_text)

    def is_gifme(self, match, text):
        """
        Response for querying a gif. Uses GiphyAPI.
        :param match: re match groups
        :param text: message text
        """
        query = match.group(1).rstrip()
        sorry = None

        if len(query) > 0:
            log.info('MATCH: gifme in {}.'.format(text))

            try:
                post_text = gif(tag=query)['data']['image_url']
            except (TypeError, IndexError):
                post_text = 'Sorry, no gifs matching those tags.'

                try:
                    sorry = gif(tag='sorry')['data']['image_url']
                except:
                    pass

            self.post(post_text)
            if sorry is not None:
                self.post(sorry)

    def is_top_scores(self, text, top=True):
        """
        Response for querying top or bottom scorers.

        :param text: message text
        """
        log.info('MATCH: topscores in "{}".'.format(text))

        if top:
            top_scores = rip_db.get_top_scores()
            post_text = '>Top 10 scores:\n'
        else:
            top_scores = rip_db.get_top_scores(False)
            post_text = '>Bottom 10 scores:\n'

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

        self.post(post_text)

    def is_new_user(self, match):
        """
        Response to new user. Welcomes them and adds them to db.
        :param match: re match groups
        """
        user_name = match.group(2)
        log.info('SYSTEM MATCH: new user detected.')

        # member = Group.list().filter(name=which_group)[0].members().filter(
        #     nickname=user_name)[0]
        member = Group.list().filter(group_id=group_id)[0].members().filter(
            nickname=user_name)[0]
        user_id = int(member.user_id)

        # check if user already in DB
        if not rip_db.exists(user_id):
            rip_db.add_player(user_id, user_name)

        points = rip_db.get_player_points(user_id)
        post_text = 'Welcome {}. You have {} points.'.format(user_name, points)

        self.post(post_text)

    def is_name_change(self, match):
        """
        Changed name in DB on nickname change.
        :param match: re match groups
        """
        user_name = match.group(1).rstrip()
        new_name = match.group(2).rstrip()
        log.info('SYSTEM MATCH: nickname change detected.')

        try:
            # member = Group.list().filter(name=which_group)[0].members().filter(
            #     nickname=new_name)[0]
            member = Group.list().filter(group_id=group_id)[0].members().filter(
                nickname=new_name)[0]
            user_id = int(member.user_id)

            # check if user already in DB
            if not rip_db.exists(user_id):
                log.warning('DB: user not found in DB but should have been. '
                            'Probably does not have any points yet.')
                return

        except IndexError:  # fallback to switching by name rather than user_id
            user_id = user_name

        rip_db.change_player_name(new_name, user_id)

        points = rip_db.get_player_points(user_id)
        post_text = 'Don\'t worry {}, you still have your {} point(s).'.format(
            new_name, points)

        self.post(post_text)


class RipDB(object):
    """
    Database holding player scores and ids
    """
    def __init__(self):
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

            # check if rip_users table exists, if not create
            sql = "SELECT EXISTS(SELECT 1 FROM information_schema.tables " \
                  "WHERE table_name='{}')".format('rip_users')

            self.cur.execute(sql)
            table_exists = self.cur.fetchone()[0]

            if not table_exists:
                log.warning('DB: table not found, creating...')
                self.set_up_table()

        except psycopg2.DatabaseError as e:
            if self.con:
                self.con.rollback()
            log.error(e)

    def set_up_table(self):
        """
        Sets up postgres table if none found.

        :return:
        """
        sql = "CREATE TABLE rip_users (" \
              "id INT PRIMARY KEY," \
              "name TEXT,"\
              "points INT"\
              ")"

        try:
            if self.con is not None:
                self.cur.execute(sql)
                log.info('DB: rip_users table created')
                self.con.commit()

        except psycopg2.DatabaseError as e:
            if self.con:
                self.con.rollback()
            log.error(e)

    def add_player(self, id, name, points=0):
        """
        Adds new player to table.
        :param id: member id number
        :param name: groupme nickname
        :param points: points to start with
        """
        sql = "INSERT INTO rip_users VALUES({}, '{}', {})"

        if self.con is not None:
            try:
                self.cur.execute(sql.format(id, name, points))
                self.con.commit()
                log.info('DB: Added {} to table with id# {} and {} point('
                         's).'.format(name, id, points))

            except psycopg2.DatabaseError as e:
                log.error(e)

        else:
            log.error('Failed adding player: not connected to DB.')

    def get_player_points(self, id):
        """
        Gets player points by name or id.
        :param id: player name or id
        :return: players points as int
        """
        if type(id) == int:
            sql = "SELECT points FROM rip_users WHERE id={}"

        else:
            sql = "SELECT points FROM rip_users WHERE LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                self.cur.execute(sql.format(id))
                points = self.cur.fetchone()

                if points is not None:
                    points = points[0]
                    log.info('DB: Fetched points of {} who has {} point(s).'.
                             format(id, points))
                else:
                    points = 0
                    id_num = self.new_id(id)
                    self.add_player(id_num, str(id), points)

                return points

            except psycopg2.DatabaseError as e:
                log.error(e)

        else:
            log.error('Failed retrieving player points: not connected to DB.')

    def add_point(self, id):
        """
        Adds point to player by name or id.
        :param id: player name or id
        :return: players points as int
        """
        if type(id) == int:
            sql = "UPDATE rip_users SET points = points + 1 WHERE id={}"

        else:
            sql = "UPDATE rip_users SET points = points + 1 WHERE " \
                  "LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                # get points first because this checks if exists or not
                cur_points = self.get_player_points(id)
                self.cur.execute(sql.format(id))
                self.con.commit()
                log.info('ADD: point to {}; now has {} point(s).'.format(id,
                                                                         cur_points+1))
                return cur_points+1

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)

        else:
            log.error('Failed adding points: not connected to DB.')

    def sub_point(self, id):
        """
        Adds point to player by name or id.
        :param id: player name or id
        :return: players points as int
        """
        if type(id) == int:
            sql = "UPDATE rip_users SET points = points - 1 WHERE id={}"

        else:
            sql = "UPDATE rip_users SET points = points - 1 WHERE " \
                  "LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                # get points first because this checks if exists or not
                cur_points = self.get_player_points(id)
                self.cur.execute(sql.format(id))
                self.con.commit()
                log.info('SUB: point to {}; now has {} point(s).'.format(id,
                                                                         cur_points-1))
                return cur_points-1

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)

        else:
            log.error('Failed adding points: not connected to DB.')

    def get_top_scores(self, top=True):
        """
        Gets top 10 scorers
        :return:
        """
        if top:
            sql = 'SELECT name, points FROM rip_users ORDER BY points DESC LIMIT 10'
        else:
            sql = 'SELECT name, points FROM rip_users ORDER BY points ASC LIMIT 10'

        log.info('DB: getting top/bottom scorers.')

        if self.con is not None:
            try:
                self.cur.execute(sql)
                top_scores = self.cur.fetchall()

                return top_scores

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)


    def change_player_name(self, new_name, id):
        """
        Changes the players name in the db
        :param new_name:
        :param id:
        :return:
        """
        if type(id) == int:
            sql = "UPDATE rip_users SET name='{}' WHERE id={}"

        else:
            sql = "UPDATE rip_users SET name='{}' WHERE LOWER(name)=LOWER('{}')"

        if self.con is not None:
            try:
                self.cur.execute(sql.format(new_name, id))
                self.con.commit()

                log.info('DB: {} name changed to {}'.format(id, new_name))

            except psycopg2.DatabaseError as e:
                self.con.rollback()
                log.error(e)

        else:
            log.error('Failed changing name: not connected to DB.')

    def new_id(self, id=None):
        """
        Generates new IDs for non players that need points
        :return: new random int
        """
        if id is not None:
            try:
                # member = Group.list().filter(name=which_group)[0].members().filter(
                #     nickname=id)[0]
                member = Group.list().filter(group_id=group_id)[0].members().filter(
                    nickname=id)[0]
                id = int(member.user_id)
                log.info('ID: Got ID from Groupme. #{}'.format(id))

            except IndexError:
                id = None

        not_taken = False

        sql = "SELECT * FROM rip_users WHERE id={}"

        if id is None:
            while not not_taken:
                try:
                    id = randint(9999999, 100000000)
                    self.cur.execute(sql.format(id))
                    ret = self.cur.fetchone()
                    if ret is None:
                        not_taken = True

                except psycopg2.DatabaseError as e:
                    log.error(e)
                    break

        if not_taken:
            log.info('ID: Got ID from random. #{}'.format(id))

        return id

    def exists(self, id):
        """
        Checks if user id already in table.
        :param id: user id #
        :return: boolean
        """
        sql = 'SELECT * FROM rip_users WHERE id={}'

        try:
            # log.info('MESSAGE: ' + repr(id))
            self.cur.execute(sql.format(id))
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
        self.app.route('/groupme', methods=['POST'])(ripbot.callback)
        self.app.run('0.0.0.0', port=port)

    def shutdown(self, signun, frame):
        """
        Gracefully shuts down flask server and ripbot.
        :param signum:
        :param frame:
        """
        self.log.info('SIGTERM: shutting down')
        sys.exit(0)

if __name__ == '__main__':
    # get groupme API key
    with open('.groupy.key', 'r') as f:
        key = f.read()

    config.API_KEY = key

    is_test = os.environ.get('IS_TEST', False)

    # which bot to use
    if is_test:
        which_bot = 'test-ripbot'
        group_id = '23373961'

    else:
        which_bot = 'ripbot'
        group_id = '13678029'

    bot = Bot.list().filter(name=which_bot)[0]

    # start server
    server = RipbotServer()
    log = server.log

    # initialize bot
    ripbot = GroupMeBot(bot.post)

    # initialize database class
    rip_db = RipDB()

    # initialize giphy
    giphy = Giphy()
    gif = giphy.random

    # init callbacks
    server.setup()