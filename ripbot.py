from __future__ import print_function

from groupy import Bot, config
from flask import Flask, request

import json
import os
import re

app = Flask(__name__)
log = app.logger


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

        if 'name' in data and data['name'] != 'ripbot':
            self.post('got it')

            if 'text' in data:
                plusplus = re.match('^@(.*?)\+\+', data['text']).group(1)
                if plusplus is not None:
                    self.post(plusplus.rstrip())


if __name__ == '__main__':
    config.API_KEY = 'Obswbyyf83EViCprfCOJHER8XbhMCd0Up99c3FBj'

    which_bot = 'ripbot'
    bot = Bot.list().filter(name=which_bot)[0]

    ripbot = GroupMeBot(bot.post)

    app.route('/groupme', methods=['POST'])(ripbot.callback)
    port = int(os.environ.get('PORT', 5000))
    app.run('0.0.0.0', port=port)