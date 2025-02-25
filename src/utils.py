import string
import random
from datetime import datetime

def GetRandomString(length:int) -> str:    
    letters = string.ascii_lowercase+string.ascii_uppercase    
    return ''.join(random.choice(letters) for i in range(length))

def MakeHumanReadableAmount(value:int) -> str:     
    if value > 1000000:
        return str(round(float(value)/1000000.0, 2))+"M"
    if value > 1000:
        return str(round(float(value)/1000.0, 1))+"k" 
        
    return str(value)

def DatetimeToString(v:datetime) -> str:
    return v.strftime("%d.%m.%Y %H:%M %Z")