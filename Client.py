import socket
import select
import sys
from Utilities.messaging import fetchMessage, sendMessage
from Utilities.terminator import Terminator

ADDR = None
PORT = None
USERNAME = None
TERMINATOR = None
SOCKS = []

def main():
    global USERNAME

    # Create socket with TCP protocol
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Connect with server
    s.connect((ADDR, PORT))

    # Wait for acknowledgement
    while True:
        ack = fetchMessage(s)
        if ack == 'ACK':
            print('Connection to server established.')
            break
        else:
            print('Could not establish connection to server.')
            sys.exit()

    # Initialize username for server
    sendMessage(s, USERNAME)
    USERNAME = fetchMessage(s)

    promptUser()

    # Send message to server
    while True:
        SOCKS = [sys.stdin, s]

        read_socks, _, _ = select.select(SOCKS , [], [])

        for sock in read_socks:
            # Incoming messages
            if sock == s:
                message = fetchMessage(sock)
                sys.stdout.write(message)

            # Outgoing message
            else:
                message = sys.stdin.readline()
                sendMessage(s, message)

            promptUser()

        if TERMINATOR.leave(): break

# UI
def promptUser():
    sys.stdout.write(f'{USERNAME}: ')
    sys.stdout.flush()

def init():
    global ADDR
    global PORT
    global USERNAME
    global TERMINATOR

    if len(sys.argv) < 2:
        print('Usage: python3 Client.py <username>')
        sys.exit()

    ADDR = '' # Allows for any interface
    PORT = 8888
    TERMINATOR = Terminator()

    USERNAME = sys.argv[1]

if __name__ == "__main__":
    init()
    main()