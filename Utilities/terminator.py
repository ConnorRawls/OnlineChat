import signal

class Terminator():
    def __init__(self):
        self.flag = False
        signal.signal(signal.SIGINT, self.changeFlag)

    def changeFlag(self, sig, frame):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.flag = True
        
    def leave(self): return self.flag