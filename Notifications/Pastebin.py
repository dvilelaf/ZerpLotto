import requests

def createPaste(name, message, config):

    data = {"api_dev_key": config['credentials']['pastebin']['api_dev_key'], 
            "api_user_key": config['credentials']['pastebin']['api_user_key'],
            "api_option": "paste", 
            "api_paste_code": message,
            "api_paste_name": name,
            "api_paste_private": "0",
            "api_paste_expire_date": "N"}

    req = requests.post("https://pastebin.com/api/api_post.php", data=data)

    if req.status_code == 200 and req.reason == 'OK':
        return req.text
    else:
        return None