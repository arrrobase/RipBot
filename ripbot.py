from __future__ import print_function

from groupy import Bot, Group, config
from flask import Flask, request
import logging

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
                plusplus = re.match('^@(.*?)\+\+', text)

                if plusplus is not None:
                    points_to = plusplus.group(1).rstrip()

                    if len(points_to) > 0:
                        log.info('MATCH: plusplus to {} in {}'.format(points_to,
                                                                      text))
                        self.post(points_to + str(member_dict[points_to]))

        return 'OK'


def set_up_db():
    con = None

    try:
        urlparse.uses_netloc.append("postgres")
        url = urlparse.urlparse(os.environ["DATABASE_URL"])

        con = psycopg2.connect(database=url.path[1:],
                               user=url.username,
                               password=url.password,
                               host=url.hostname,
                               port=url.port
                               )
        log.info('Connected to DB')

        cur = con.cursor()

        sql = 'CREATE TABLE Ids(id INTEGER PRIMARY KEY, name TEXT, points ' \
              'INTEGER)'
        cur.execute(sql)

        sql = 'INSERT INTO Ids VALUES({}, \'{}\', {})'
        for key, value in member_dict.items():
            cur.execute(sql.format(value, key, 0))

        log.info('Players added to DB')
        con.commit()

    except psycopg2.DatabaseError as e:
        if con:
            con.rollback()
        print(e)


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

    set_up_db()

    port = int(os.environ.get('PORT', 5000))
    app.route('/groupme', methods=['POST'])(ripbot.callback)
    app.run('0.0.0.0', port=port)