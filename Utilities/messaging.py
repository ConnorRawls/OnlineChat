import socket

# Receive message
def fetchMessage(conn):
    data = ''
    size_ex = None

    while True:
        buff = conn.recv(1024)

        if size_ex is None:
            buff = buff.decode().split(',')
            size_ex = int(buff[0]) # Extract expected message size
            del buff[0] # Remove size indicator
            if len(buff) > 1: buff = ','.join(buff).encode()
            else: buff = ''.join(buff).encode() # Recode

        data = data + buff.decode()

        if len(data.encode()) >= size_ex: break

    return data

# Send message
def sendMessage(*argv):
    # Needs ability for arg overload due to Thread.action call
    if len(argv) == 2:
        s = argv[0]
        message = argv[1]
    else:
        s = argv[0][0]
        message = argv[0][1]

    try: message = message.decode() # We need a str object to continue
    except (UnicodeDecodeError, AttributeError): pass

    size_ex = len(message.encode())
    message = str(size_ex) + ',' + message
    message = message.encode()
    unsent_data = len(message)
    sent_data = 0

    while True:
        buff = s.send(message[sent_data:])
        if buff >= unsent_data: break
        if sent_data >= unsent_data: break
        else: sent_data += buff