class YSDBException(Exception):
    def __init__(self, message:str, related_exception:BaseException|None = None):         
        super().__init__(message)
        self.message = message
        self.related_exception = related_exception

    def FormatMessage(self) -> str:
        return self.message

    def __str__(self):
        result = self.FormatMessage()

        if not (self.related_exception is None):
            result += " || Related exception: "+str(self.related_exception)

        return result   