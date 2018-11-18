from Notifications import TelegramNotifier, TwitterNotifier, Pastebin

def paymentNotify(payment, record, config):

    TXlink = TwitterNotifier.ShortenURL().Shorten(config['links']['bithomp'] + payment.TXid)

    # Prepare messages
    message = None

    if payment.TXtype == 'PRIZE':

        participantTXs = record.participantTXids.replace(' ','').split(',')

        pastebinlink = Pastebin.createPaste('ZerpLotto participant TXs for prize {}'.format(record.id),
                                            ('\n').join(participantTXs),
                                            config)

        message = 'A new ZerpLotto prize has been sent. Congratulations to the winner!\n' \
                  'Amount: {} XRP\n' \
                  'Winner: {}\n' \
                  'Prize TX: {}\n' \
                  'Participant TXs: {}' \
                  .format(payment.amount, payment.destination, TXlink, pastebinlink)

        TwitterNotifier.postUpdate(message, config)

    elif payment.TXtype == 'FEE':

        message = 'A new ZerpLotto fee has been sent.\n' \
                  'Amount: {} XRP\n' \
                  'Destination: {}\n' \
                  'Fee TX: {}\n' \
                  .format(payment.amount, payment.destination, TXlink)

    elif payment.TXtype == 'DONATION':

        charityName = ''
        for i in config['accounts']['donations']:
            if config['accounts']['donations'][i]['address'] == payment.destination:
                charityName = i
                break

        message = 'A new ZerpLotto donation has been sent.\n' \
                  'Amount: {} XRP\n' \
                  'Destination: {}\n' \
                  'Prize TX: {}' \
                  .format(payment.amount, charityName, TXlink)

        TwitterNotifier.postUpdate(message, config)


    TelegramNotifier.sendMessage(message, config)
