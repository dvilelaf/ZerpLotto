from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import logging
import json
import os
import Ledger
from peewee import *
from DBmodels import *

# Load configuration
config = None
testing = True
configFilePath = 'configTest.json' if testing else 'config.json'
lockFileName = 'ZerpLottoLock'

with open(configFilePath, 'r') as configFile:
    config = json.load(configFile) # TODO: validate json scheme

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Create ledger
ledger = Ledger.Ledger(config['parameters']['connection'])

# Create database connection
db.init(config['parameters']['database'])


def status(bot, update):

    try:

        db.connect(reuse_if_open=True)

        participants = Participant.select()

        prizestatus = {p: {'participants': 0, 'balance': 0} for p in config['parameters']['prizes']}

        totalPlayedBalance = 0

        for p in participants:
            prizestatus[p.prize]['participants'] += 1
            prizestatus[p.prize]['balance'] += p.amount

        message = ''

        for p in prizestatus:

            percent = round(prizestatus[p]['balance'] / float(p) * 100)

            message += 'PRIZE: {}\n' \
                    '- Participants: {}\n' \
                    '- Balance: {} XRP ({}%)\n' \
                    .format(p,
                            prizestatus[p]['participants'],
                            round(prizestatus[p]['balance'], 4),
                            percent)

            totalPlayedBalance += float(prizestatus[p]['balance'])

        message += 'PLAYED BALANCE: {}'.format(totalPlayedBalance)

        update.message.reply_text(message)

    except OperationalError:

        update.message.reply_text('Empty database!')

    finally:

        db.close()


def last(bot, update):

    try:

        with open('log', 'r') as log:

            data = log.read()

            startIndex = data.rfind('Lotto execution started on')
            endIndex = data.rfind('Lotto execution finished on')

            startTime = data[startIndex+27:startIndex+46]
            endTime = data[endIndex+28:endIndex+47]

            #startTime = datetime.datetime.strptime(data[startIndex+27:startIndex+46], '%Y-%m-%d %H:%M:%S')
            #endTime = datetime.datetime.strptime(data[endIndex+28:endIndex+47], '%Y-%m-%d %H:%M:%S')

            message = 'Last logged execution started:\n {} \n' \
                    'Last logged execution finished:\n {} \n' \
                    .format(startTime, endTime)

            update.message.reply_text(message)

    except FileNotFoundError:

        update.message.reply_text('No log yet!')


def balance(bot, update):

    accountInfo = ledger.getAccountInfo(config['accounts']['lotto']['address'])
    accountInfo['account_data']['Balance'] = int(accountInfo['account_data']['Balance']) / 1e6

    message = 'Available balance: {} XRP'.format(round(float(accountInfo['account_data']['Balance']) - config['parameters']['reservedXRP'], 4))
    update.message.reply_text(message)


def listPayments(bot, update):

    try:

        db.connect(reuse_if_open=True)

        pendingPayments = Payment.select().where(Payment.status == 'PENDING')

        message = []

        for p in pendingPayments:

            message += 'Payment ID {}:\n' \
                       'Type: {}\n' \
                       'Destination: {}\n' \
                       'Amount: {}\n' \
                       '-----------------\n' \
                       .format(p[id], p[TXtype], p[destination], p[amount])

        update.message.reply_text(message)


    except OperationalError:

        update.message.reply_text('Empty database!')

    finally:

        db.close()


def lock(bot, update):
    if os.path.isfile(lockFileName):
        update.message.reply_text('Already locked')
    else:
        open(lockFileName, 'w')
        update.message.reply_text('Locked')


def unlock(bot, update):
    if os.path.isfile(lockFileName):
        os.remove(lockFileName)
        update.message.reply_text('Unlocked')
    else:
        update.message.reply_text('Already unlocked')


def text(bot, update):
    update.message.reply_text('Available commands:\n/balance\n/status\n/last\n/lock\n/unlock\n/listPayments')


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


def main():

    # Create the EventHandler and pass it your bot's token.
    updater = Updater(config['credentials']['telegram']['key'])

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Owner username
    user = config['credentials']['telegram']['username']

    # Add handlers
    dp.add_handler(CommandHandler("status", status, filters=Filters.user(username=user)))
    dp.add_handler(CommandHandler("last", last, filters=Filters.user(username=user)))
    dp.add_handler(CommandHandler("balance", balance, filters=Filters.user(username=user)))
    dp.add_handler(CommandHandler("lock", lock, filters=Filters.user(username=user)))
    dp.add_handler(CommandHandler("unlock", unlock, filters=Filters.user(username=user)))
    dp.add_handler(CommandHandler("listPayments", listPayments, filters=Filters.user(username=user)))
    dp.add_handler(MessageHandler((Filters.text & Filters.user(username=user)), text))
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
