import socket
import _thread
import threading
from Utilities.messaging import *
from Utilities.terminator import Terminator

ADDR = None
PORT = None
TERMINATOR = None
ERROR_MSG = {}
CONNS = []
USERNAMES = {}
GROUPS = {}
CLIENTS = {}
PRINT_LOCK = threading.Lock()
WELCOME_MSG = None
HELP_MSG = None

# Handles all client actions after initial connection
class Client:
    def __init__(self, conn, username):
        global CLIENTS
        CLIENTS[username] = self
        self.conn = conn
        self.username = username
        self.groups = []
        self.action = {
            'BROADCAST' : broadcast,
            'GROUPCHAT' : broadcast,
            'CREATEGROUP' : createGroup,
            'JOINGROUP' : joinGroup,
            'LEAVEGROUP' : leaveGroup,
            'LIST_ACTIVEGROUPS' : sendMessage,
            'LIST_ALLGROUPS' : sendMessage,
            'LIST_ONLINE' : sendMessage,
            'PM' : sendMessage,
            'HELP' : sendMessage,
            'ERROR' : sendMessage
        }
        self.interact()

    def interact(self):
        while True:
            try:
                # Determine what client wishes to do
                message = fetchMessage(self.conn)
                action, args = fetchAction(message, self)
                # Conduct action
                self.action[action](args)
                
            # Client has gone offline
            except:
                PRINT_LOCK.acquire()
                print(f'{str(self.conn.getpeername())} {self.username} has gone offline.')
                PRINT_LOCK.release()
                broadcast(self.conn, f'\r{self.username} has gone offline.\n')
                break

        self.destruct()

    def destruct(self):
        global CONNS
        global USERNAMES
        global GROUPS
        for group in self.groups:
            group = GROUPS[group]
            if len(group.group_users) == 1:
                del GROUPS[group.groupname]
            elif self.username == group.owner:
                for user in group.group_users:
                    group.owner = user
                    break
            group.rmvUser(self.username)
        
        self.conn.close()
        CONNS.remove(self.conn)
        del USERNAMES[self.username]

# Clients can form their own private groups (channels?)
class Group:
    def __init__(self, groupname, username):
        self.groupname = groupname
        self.owner = username
        self.group_users = {}
        self.group_conns = []
        self.addUser(self.owner)

    def addUser(self, username):
        global CLIENTS
        conn = USERNAMES[username]
        self.group_users[username] = conn
        self.group_conns.append(conn)
        grp_message = f'{username} has joined group {self.groupname}.\n'
        broadcast(conn, grp_message, self.group_conns)
        CLIENTS[username].groups.append(self.groupname)

    def rmvUser(self, username):
        global CLIENTS
        conn = self.group_users[username]
        grp_message = f'{username} has just left group {self.groupname}.\n'
        broadcast(conn, grp_message, self.group_conns)
        del self.group_users[username]
        self.group_conns.remove(conn)
        CLIENTS[username].groups.remove(self.groupname)

def main():
    global CONNS
    global USERNAMES

    # Create socket with TCP protocol
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind socket
    server_sock.bind((ADDR, PORT))

    # Listen for client connection
    server_sock.listen(1)

    PRINT_LOCK.acquire()
    print('Server is online.')
    PRINT_LOCK.release()

    # Listen for new clients entering chat
    while True:
        conn, addr = server_sock.accept()
        CONNS.append(conn)

        # Send acknowledgement
        sendMessage(conn, 'ACK')

        # Request username (TODO needs own thread)
        username = fetchMessage(conn)
        username = resolveDupUser(username)

        # Confirm username
        USERNAMES[username] = conn
        sendMessage(conn, username)

        PRINT_LOCK.acquire()
        print(f'{str(conn.getpeername())} {username} is now online.')
        PRINT_LOCK.release()

        broadcast(conn, f'\r{username} is now online.\n')

        # Create new thread to handle client from here on out
        _thread.start_new_thread(Client, (conn, username))

        # Send welcome message
        sendMessage(conn, WELCOME_MSG)

        if TERMINATOR.leave(): break

    for conn in CONNS: conn.close()
    server_sock.close()

    print('Closing server.')

# Send message to all clients
def broadcast(*argv):
    global CONNS
    global USERNAMES

    # Needs ability for arg overload due to Thread.action call
    if len(argv) == 3:
        ignore_sock = argv[0]
        message = argv[1]
        conns = argv[2]
    if len(argv) == 2:
        ignore_sock = argv[0]
        message = argv[1]
        conns = CONNS
    elif len(argv) == 1:
        if len(argv[0]) == 2:
            ignore_sock = argv[0][0]
            message = argv[0][1]
            conns = CONNS
        else:
            ignore_sock = argv[0][0]
            message = argv[0][1]
            conns = argv[0][2]

    username = list(USERNAMES.keys())[list(USERNAMES.values()).index(ignore_sock)]
    message = f'\r{message}'

    for conn in conns:
        if conn != ignore_sock:
            try:
                sendMessage(conn, message)
            except:
                conn.close()
                CONNS.remove(conn)
                del USERNAMES[list(USERNAMES.keys())[list(USERNAMES.values()).index(conn)]]

# Parse client message for action
def fetchAction(message, self):
    action = None
    args = None
    msg_split = message.split(' ')
        
    if '/' in msg_split[0]:
        command = msg_split[0]
        action = msg_split[0].replace('/', '')
        action = action.replace('\n', '') # Why is this here in the first place
        message = message.replace(f'{command} ', '', 1)

    # Default to broadcasting
    else:
        action = 'BROADCAST'
        srv_msg = f'{str(self.conn.getpeername())} {self.username}: {message}'
        message = f'\r{self.username}: {message}'
        args = (
            self.conn, message
        )
        PRINT_LOCK.acquire()
        print(srv_msg)
        PRINT_LOCK.release()
        return action, args

    # Private group broadcasting
    if action == 'gc':
        action = 'GROUPCHAT'
        groupname = msg_split[1].replace('\n', '')
        print(f'"{groupname}"')
        group = GROUPS[groupname]
        self_username = self.username
        self_conn = self.conn
        if self_username not in group.group_users:
            action = 'ERROR'
            err_msg = ERROR_MSG['NOT_MEMBER']
            args = (self_conn, err_msg)
            return action, args
        message = message.replace(f'{groupname} ', '', 1)
        srv_msg = f'({groupname}) {str(self_conn.getpeername())} {self_username}: {message}'
        message = f'({groupname}) {self_username}: {message}'
        group_conns = GROUPS[groupname].group_conns
        args = (self_conn, message, group_conns)
        PRINT_LOCK.acquire()
        print(srv_msg)
        PRINT_LOCK.release()
        return action, args

    elif action == 'lo':
        action = 'LIST_ONLINE'
        message = ''
        for username in USERNAMES:
            message = '\r' + username + '\n'
        self_conn = self.conn
        args = (self_conn, message)
        return action, args

    # Join a private group
    elif action == 'jg':
        action = 'JOINGROUP'
        groupname = msg_split[1].replace('\n', '')
        if groupname not in GROUPS:
            action = 'ERROR'
            self_conn = self.conn
            err_msg = ERROR_MSG['UNKNOWN_GROUP']
            args = (self_conn, err_msg)
            return action, args
        self_username = self.username
        group = GROUPS[groupname]
        if self_username in group.group_users:
            action = 'ERROR'
            self_conn = self.conn
            err_msg = ERROR_MSG['ALREADY_MEMBER']
            args = (self_conn, err_msg)
            return action, args
        args = (group, self)
        return action, args

    # Create a new private group
    elif action == 'cg':
        action = 'CREATEGROUP'
        groupname = msg_split[1].replace('\n', '')
        if groupname in GROUPS:
            self_conn = self.conn
            action = 'ERROR'
            err_msg = ERROR_MSG['DUPLICATE_GROUP']
            args = (self_conn, err_msg)
            return action, args
        args = (groupname, self)
        return action, args

    # Leave a private group
    elif action == 'lg':
        action = 'LEAVEGROUP'
        groupname = msg_split[1].replace('\n', '')
        self_username = self.username
        if groupname not in GROUPS:
            action = 'ERROR'
            err_msg = ERROR_MSG['UNKNOWN_GROUP']
            self_conn = self.conn
            args = (self_conn, err_msg)
            return action, args
        group = GROUPS[groupname]
        if self_username not in group.group_users:
            action = 'ERROR'
            self_conn = self.conn
            err_msg = ERROR_MSG['NOT_MEMBER']
            args = (self_conn, err_msg)
            return action, args
        args = (group, self)
        return action, args

    # List groups client is a member of
    elif action == 'listg':
        action = 'LIST_ACTIVEGROUPS'
        message = ''
        if len(self.groups) > 0:
            for groupname in self.groups:
                message = ' ' + message + groupname + ','
            message = message[1:]
            message = message[:-1]
            message = '\r' + message + '\n'
        else: message = '\r\n'
        self_conn = self.conn
        args = (self_conn, message)
        return action, args

    elif action == 'listallg':
        action = 'LIST_ALLGROUPS'
        message = ''
        if len(GROUPS) > 0:
            for groupname in GROUPS:
                message = ' ' + message + groupname + ','
            message = message[1:]
            message = message[:-1]
            message = '\r' + message + '\n'
        else: message = '\r\n'
        self_conn = self.conn
        args = (self_conn, message)
        return action, args

    # Client wishes to view help message
    elif action == 'help':
        action = 'HELP'
        conn = self.conn
        args = (conn, HELP_MSG)
        return action, args

    # Client wishes to send a private message
    elif action == 'pm':
        action = 'PM'
        username = msg_split[1]
        message = message.replace(f'{username} ', '', 1)
        self_username = self.username
        if username not in USERNAMES:
            conn = self.conn
            action = 'ERROR'
            err_msg = ERROR_MSG['UNKNOWN_USER']
            args = (conn, err_msg)
            return action, args
        else:
            self_username = self.username
            recv_conn = USERNAMES[username]
            message = f'\r(PM) {self_username}: {message}'
            args = (recv_conn, message)
        return action, args
    
    # Unknown command
    else:
        action = 'ERROR'
        conn = self.conn
        err_msg = ERROR_MSG['UNKNOWN_COMMAND']
        args = (conn, err_msg)
        return action, args

# Python does not allow object templates as callable
# We need helper functions to facilitate this
def createGroup(*argv):
    global GROUPS
    groupname = argv[0][0]
    self = argv[0][1]
    self_username = self.username
    GROUPS[groupname] = Group(groupname, self_username)
    message = f'Group {groupname} created.\n'
    conn = USERNAMES[self_username]
    sendMessage(conn, message)

def joinGroup(*argv):
    group = argv[0][0]
    self = argv[0][1]
    self.groups.append(group.groupname)
    groupname = group.groupname
    self_username = self.username
    group.addUser(self_username)
    srv_msg = f'{self_username} has joined {groupname}.'
    PRINT_LOCK.acquire()
    print(srv_msg)
    PRINT_LOCK.release()

def leaveGroup(*argv):
    group = argv[0][0]
    self = argv[0][1]
    groupname = group.groupname
    self_username = self.username
    group.rmvUser(self_username)
    srv_msg = f'{self_username} has left {groupname}.'
    PRINT_LOCK.acquire()
    print(srv_msg)
    PRINT_LOCK.release()

# Ensure no two clients have the same username
def resolveDupUser(self_username):
    i = 0
    while True:
        repeat = False
        for username in USERNAMES:
            if self_username == username: # Duplicate username detected
                i += 1
                self_username = self_username + str(i)
                repeat = True
        if repeat == False: break

    return self_username

# Should probably move vars to separate file
def init():
    global ADDR
    global PORT
    global TERMINATOR
    global WELCOME_MSG
    global HELP_MSG
    global ERROR_MSG

    ADDR = '' # Allows for any interface
    PORT = 8888
    TERMINATOR = Terminator()
    WELCOME_MSG = 'Welcome to the chat :)\nTo view instructions, type /help\n'
    HELP_MSG = \
        '\n* Messages are broadcasted by default. *\n' \
        '/help    View command options.\n' \
        '/pm <username> <message>   Send user a private message.\n' \
        '/gc <groupname> <message>   Send message to private group.\n' \
        '/cg <groupname>    Create a private group.\n' \
        '/jg <groupname>    Join a private group.\n' \
        '/lg <groupname>    Leave a private group.\n' \
        '/listg    List groups you are a member of.\n'
    ERROR_MSG = {
        'UNKNOWN_COMMAND' : '\nUnknown command.\nType /help for a list of possible comands.\n',
        'UNKNOWN_USER' : 'User could not be found :(\n',
        'DUPLICATE_GROUP' : 'A group with that name already exists.\n',
        'NOT_MEMBER': 'You are not a member of this group.\n',
        'UNKNOWN_GROUP': 'This group does not exist.\n',
        'ALREADY_MEMBER' : 'You are already a member of this group.\n'
    }

if __name__ == "__main__":
    init()
    main()