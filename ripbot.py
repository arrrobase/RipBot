from __future__ import print_function

from groupy import Bot, Group, config
from flask import Flask, request
import logging

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
            text = data['system']

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

    app.route('/groupme', methods=['POST'])(ripbot.callback)
    port = int(os.environ.get('PORT', 5000))
    app.run('0.0.0.0', port=port)