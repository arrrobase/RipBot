from __future__ import print_function

from groupy import Bot, Group, config
from flask import Flask, request
import logging

from random import randint
import urllib.parse as urlparse
import psycopg2
import json
import sys
import os
import re

app = Flask(__name__)
log = app.logger
log.addHandler(logging.StreamHandler(sys.stdout))
log.setLevel(logging.INFO)


class GroupMeBot(object):
    """
    Simple groupme bot
    """
    def __init__(self, post):
        self.post = post

    def callback(self):
        """
        Method to send responses on callbacks.
        """
        data = json.loads(request.data.decode('utf8'))

        name = None
        text = None
        system = None

        if 'name' in data:
            name = data['name']

        if 'text' in data:
            text = data['text']

        if 'system' in data:
            system = data['system']

        if name is not None and name != 'ripbot':
            log.info('Got user message, parsing...')

            if text is not None:
                plusplus =   re.match('^@(.*?) \+\+ (.*)', text)
                minusminus = re.match('^@(.*?) \-\- (.*)', text)

                if plusplus is not None:
                    points_to = plusplus.group(1)
                    what_for = plusplus.group(2).lstrip('for ')

                    if len(points_to) > 0:
                        log.info('MATCH: plusplus to {} in {}'.format(points_to,
                                                                      text))

                        rip_db.add_point(points_to)
                        points = rip_db.get_player_points(points_to)
                        post_text = '{} now has {} point(s), ' \
                                    'most recently for {}.'.format(points_to,
                                                                   points,
                                                                   what_for)

                        self.post(post_text)

                if minusminus is not None:
                    points_to = minusminus.group(1)
                    what_for = minusminus.group(2).lstrip('for ')

                    if len(points_to) > 0:
                        log.info('MATCH: minusminus to {} in {}'.format(points_to,
                                                                      text))

                        rip_db.sub_point(points_to)
                        points = rip_db.get_player_points(points_to)
                        post_text = '{} now has {} points, ' \
                                    'most recently for {}.'.format(points_to,
                                                                   points, what_for)

                        self.post(post_text)

        return 'OK'


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
#         log.info('Connected to DB')
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
#         log.info('Players added to DB')
#         con.commit()
#
#     except psycopg2.DatabaseError as e:
#         if con:
#             con.rollback()
#         print(e)


class Rip_DB(object):
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
            urlparse.uses_netloc.append('postgres')
            url = urlparse.urlparse(os.environ['DATABASE_URL'])

            self.con = psycopg2.connect(database=url.path[1:],
                                        user=url.username,
                                        password=url.password,
                                        host=url.hostname,
                                        port=url.port
                                        )
            log.info('Successfully connected to database')

            self.cur = self.con.cursor()

        except psycopg2.DatabaseError as e:
            if self.con:
                self.con.rollback()
            log.error(e)

    def add_player(self, id, name, points=0):
        """
        Adds new player to table
        :param id:
        :param name:
        :param points:
        """
        sql = 'INSERT INTO Ids VALUES({}, \'{}\', {})'

        if self.con is not None:
            try:
                self.cur.execute(sql.format(id, name, points))
                self.con.commit()
                log.info('Added {} to table with id# {} and {} point('
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
                    log.info('Fetched points of {} who has {} point(s).'.format(id,
                                                                          points))
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
                cur_points = self.get_player_points(id)
                self.cur.execute(sql.format(id))
                self.con.commit()
                log.info('Added point to {}; now has {} point(s).'.format(id,
                                                                          cur_points+1))

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
                cur_points = self.get_player_points(id)
                self.cur.execute(sql.format(id))
                self.con.commit()
                log.info('Added point to {}; now has {} point(s).'.format(id,
                                                                          cur_points+1))

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

        sql = "UPDATE Ids SET points = points + 1 WHERE id={}"

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



if __name__ == '__main__':
    config.API_KEY = 'Obswbyyf83EViCprfCOJHER8XbhMCd0Up99c3FBj'

    which_bot = 'ripbot'
    bot = Bot.list().filter(name=which_bot)[0]

    ripbot = GroupMeBot(bot.post)

    which_group = 'bot_Test'
    group = Group.list().filter(name=which_group)[0]

    member_dict = {}
    for member in group.members():
        member_dict[member.nickname] = int(member.user_id)

    # set_up_db()
    rip_db = Rip_DB()

    port = int(os.environ.get('PORT', 5000))
    app.route('/groupme', methods=['POST'])(ripbot.callback)
    app.run('0.0.0.0', port=port)