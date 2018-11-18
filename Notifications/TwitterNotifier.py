import twitter
try:
    from urllib.request import urlopen
except:
    from urllib2 import urlopen

def postUpdate(message, config):

    api = twitter.Api(consumer_key        = config['credentials']['twitter']['consumer_key'],
                      consumer_secret     = config['credentials']['twitter']['consumer_secret'],
                      access_token_key    = config['credentials']['twitter']['access_token_key'],
                      access_token_secret = config['credentials']['twitter']['access_token_secret'])

    #print(api.VerifyCredentials())

    return api.PostUpdate(message)


class ShortenURL(object):
    """ A class that defines the default URL Shortener.
    TinyURL is provided as the default and as an example helper class to make
    URL Shortener calls if/when required. """

    def __init__(self,
                 userid=None,
                 password=None):
        """Instantiate a new ShortenURL object. TinyURL, which is used for this
        example, does not require a userid or password, so you can try this
        out without specifying either.
        Args:
            userid:   userid for any required authorization call [optional]
            password: password for any required authorization call [optional]
        """
        self.userid = userid
        self.password = password

    def Shorten(self,
                long_url):
        """ Call TinyURL API and returned shortened URL result.
        Args:
            long_url: URL string to shorten
        Returns:
            The shortened URL as a string
        Note:
            long_url is required and no checks are made to ensure completeness
        """

        result = None
        f = urlopen("http://tinyurl.com/api-create.php?url={0}".format(
            long_url))
        try:
            result = f.read()
        finally:
            f.close()

        # The following check is required for py2/py3 compatibility, since
        # urlopen on py3 returns a bytes-object, and urlopen on py2 returns a
        # string.
        if isinstance(result, bytes):
            return result.decode('utf8')
        else:
            return result