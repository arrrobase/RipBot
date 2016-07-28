"""
Groupme bot running on Heroku.
"""

# Copyright (C) 2016 Alexander Tomlinson
# Distributed under the terms of the GNU General Public License (GPL).

from __future__ import print_function

from groupy import Bot, Group, config
from flask import Flask, request
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

        last_message = Group.list().filter(name=which_group)[0].messages().\
            newest.text

        if last_message != 'Idling... Goodbye.':
            self.post('RIPBOT IS BACK!!!')

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
                new_user = re.match('(.*?) added (.*?) to the group', text)
                name_change = re.match('')

                if new_user is not None:
                    self.is_new_user(new_user)

                else:
                    log.info('No matches; ignoring.')

        # non system messages not originating from ripbot
        elif name is not None and name != 'ripbot':
            log.info('BOT: Got user message, parsing...')

            if text is not None:
                # matches string in format: '@First Last ++ more text'
                plusplus =   re.match('^@(.*?) \+\+(.*)', text)
                minusminus = re.match('^@(.*?) \-\-(.*)', text)

                if plusplus is not None:
                    self.is_plusplus(plusplus, text)

                elif minusminus is not None:
                    self.is_minusminus(minusminus, text)

                else:
                    log.info('No matches; ignoring.')

    def is_plusplus(self, match, text):
        """
        Response for adding points
        :param match: re match groups
        :param text: message text
        """
        points_to = match.group(1).rstrip()
        what_for = match.group(2).lstrip(' for ')
        # if no reason given
        if not what_for:
            what_for = 'nothing'

        if len(points_to) > 0:
            log.info('MATCH: plusplus to {} in {}.'.format(points_to,
                                                           text))

            points = rip_db.add_point(points_to)
            post_text = '{} now has {} point(s), ' \
                        'most recently for {}.'.format(points_to,
                                                       points,
                                                       what_for)

            self.post(post_text)

    def is_minusminus(self, match, text):
        """
        Response for subtracting points
        :param match: re match groups
        :param text: message text
        """
        points_to = match.group(1).rstrip()
        what_for = match.group(2).lstrip(' for ')
        # if no reason given
        if not what_for:
            what_for = 'nothing'

        if len(points_to) > 0:
            log.info('MATCH: minusminus to {} in {}.'.format(points_to,
                                                             text))

            points = rip_db.sub_point(points_to)
            post_text = '{} now has {} points, ' \
                        'most recently for {}.'.format(points_to,
                                                       points,
                                                       what_for)

            self.post(post_text)

    def is_new_user(self, match):
        """
        Response to new user. Welcomes them and adds them to db.
        :param match: re match groups
        """
        user_name = match.group(2)
        log.info('SYSTEM MATCH: new user detected.')

        member = Group.list().filter(name=which_group)[0].members().filter(
            nickname=user_name)[0]
        user_id = int(member.user_id)

        # check if user already in DB
        if not rip_db.exists(user_id):
            # TODO: PROBLEM could add new user with ID number of existing,
            # very unlikely given 8 digit int, but make a check anyway
            rip_db.add_player(user_id, user_name)

        points = rip_db.get_player_points(user_id)
        post_text = 'Welcome {}. You have {} points.'.format(user_name, points)
        self.post(post_text)

    def goodbye(self):
        """
        Exit message.
        """
        self.post('Idling... Goodbye.')


# def set_up_db():
#     con = None
#
#     try:
#         urlparse.uses_netloc.append("postgres")
#         url = urlparse.urlparse(os.environ["DATABASE_URL"])
#
#         con = psycopg2.connect(database=url.path[1:],
#                                user=url.username,
#                                password=url.password,
#                                host=url.hostname,
#                                port=url.port
#                                )
#         log.info('DB: Connected to DB')
#
#         cur = con.cursor()
#
#         sql = 'CREATE TABLE Ids(id INTEGER PRIMARY KEY, name TEXT, points ' \
#               'INTEGER)'
#         cur.execute(sql)
#
#         sql = 'INSERT INTO Ids VALUES({}, \'{}\', {})'
#         for key, value in member_dict.items():
#             cur.execute(sql.format(value, key, 0))
#
#         log.info('DB: Players added to DB')
#         con.commit()
#
#     except psycopg2.DatabaseError as e:
#         if con:
#             con.rollback()
#         print(e)


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
        sql = 'INSERT INTO Ids VALUES({}, \'{}\', {})'

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
            sql = "SELECT points FROM Ids WHERE id={}"

        else:
            sql = "SELECT points FROM Ids WHERE name='{}'"

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
                    id_num = self.new_id()
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
            sql = "UPDATE Ids SET points = points + 1 WHERE id={}"

        else:
            sql = "UPDATE Ids SET points = points + 1 WHERE name='{}'"

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
            sql = "UPDATE Ids SET points = points - 1 WHERE id={}"

        else:
            sql = "UPDATE Ids SET points = points - 1 WHERE name='{}'"

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

    def new_id(self):
        """
        Generates new IDs for non players that need points
        :return: new random int
        """
        id = None
        not_taken = False

        sql = "SELECT * FROM Ids WHERE id={}"

        while id is None or not_taken is False:
            try:
                id = randint(9999999, 100000000)
                self.cur.execute(sql.format(id))
                ret = self.cur.fetchone()
                if ret is None:
                    not_taken = True

            except psycopg2.DatabaseError as e:
                log.error(e)
                break

        return id

    def exists(self, id):
        """
        Checks if user id already in table.
        :param id: user id #
        :return: boolean
        """
        sql = 'SELECT * FROM Ids WHERE id={}'

        try:
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
        ripbot.goodbye()
        # self.log.info('SIGTERM: shutting down')
        sys.exit(0)

if __name__ == '__main__':
    # get groupme API key
    with open('.groupy.key', 'r') as f:
        key = f.read()

    config.API_KEY = key

    # which bot to use
    which_bot = 'ripbot'
    bot = Bot.list().filter(name=which_bot)[0]

    # to set up initial postgres member database
    # bot's groupme
    which_group = 'bot_Test'
    # group = Group.list().filter(name=which_group)[0]
    #
    # member_dict = {}
    # for member in group.members():
    #     member_dict[member.nickname] = int(member.user_id)
    # set_up_db()

    # start server
    server = RipbotServer()
    log = server.log

    # initialize bot
    ripbot = GroupMeBot(bot.post)

    # initialize database class
    rip_db = RipDB()

    # init callbacks
    server.setup()