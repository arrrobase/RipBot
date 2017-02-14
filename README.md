## RipBot GroupMe bot

### What is it?

A Groupme bot built on Flask, hosted with Heroku. Simple message parsing and
fun responses. Can request images or gifs.

### Licensing

RipBot is licensed under GNU GPL v3.0.

### Install

Clone this repo, set the proper url callback (what you chose in your Heroku instance) in server setup(). Configure the proper environment
variables in Heroku (i.e. Groupy key, Google key, Giphy key, etc...). Enable postgres in Heroku. Push the repo and it should initialise
the database and start listening to whichever bots you point to that Heroku address. 
