import telegram

def sendMessage(message, config):
    """Sends a simple message."""
    bot = telegram.Bot(token=config['credentials']['telegram']['key'])
    bot.send_message(chat_id=config['credentials']['telegram']['chat_id'], text=message)

