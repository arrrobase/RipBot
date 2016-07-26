from __future__ import print_function

from groupy import Bot, config
from flask import Flask, request

import json

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
        print('it worked!')
        self.post('did it work?')


if __name__ == '__main__':
    config.API_KEY = 'Obswbyyf83EViCprfCOJHER8XbhMCd0Up99c3FBj'

    which_bot = 'ripbot'
    bot = Bot.list().filter(name=which_bot)[0]

    ripbot = GroupMeBot(bot.post)

    app.route('/', methods=['POST'])(ripbot.callback)
    app.run('0.0.0.0', port=5000)