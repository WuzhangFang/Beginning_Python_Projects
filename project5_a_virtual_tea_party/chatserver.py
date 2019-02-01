from asyncore import dispatcher
from asynchat import async_chat
import socket, asyncore

PORT = 5005
NAME = 'TestChat'

class EndSession(Exception): pass

class CommandHandler:
    """
    Simple command handler similar to cmd.Cmd from the standard library.
    """
    def unknown(self, session, cmd):
        'Respond to an unknown command'
        session.push('Unknown command: {}s\r\n'.format(cmd))
    
    def handle(self, session, line):
        'Handle a received line from a given session'
        if not line.strip(): return
        
        parts = line.split(' ', 1)
        cmd = parts[0]
        try: 
            line = parts[1].strip()
        except IndexError:
            line = ''
        # Try to find a handler
        meth = getattr(self, 'do_' + cmd, None)
        try:
            # assume it's callable
            meth(session, line)
        except TypeError:
            # if not, respond to the unknown command
            self.unknown(session, cmd)

class Room(CommandHandler):
    """
    A generic environment that contain one or more users (sessions).
    It takes care of basic command handling and broadcasting.
    """
    def __init__(self, server):
        self.server = server
        self.sessions = []
    
    def add(self, session):
        'A session (user) has entered the room'
        self.sessions.append(session)
    
    def remove(self, session):
        'A session (user) has left the room'
        self.sessions.remove(session)
    
    def broadcast(self, line):
        'Send a line to all sessions in the room'
        for session in self.sessions:
            session.push(line)

    def do_logout(self, session, line):
        'Respond to the logout command'
        raise EndSession

class LoginRoom(Room):
    """
    A room meant for a single person who has just connected.
    """
    def add(self, session):
        Room.add(self, session)
        # When a user enters, greet him/her:
        self.broadcast('Welcome to {}\r\n'.format(self.server.name))
    
    def unknown(self, session, cmd):
        session.push('Please log in\nUse "log in <nick>"\r\n')
    
    def do_login(self, session, line):
        name = line.strip()
        if not name:
            session.push('Please enter a name\r\n')
        elif name in self.server.users:
            session.push('The name "{}" is taken.\r\n'.format(name))
            session.push('Please try again.\r\n')
        else:
            session.enter(self.server.main_room)

class ChatRoom(Room):
    """
    A room meant for multiple users who can chat with the others.
    """
    def add(self, session):
        self.broadcast(session.name + ' has entered the room.\r\n')
        self.server.users[session.name] = session
        super().add(session)
    
    def remove(self, session):
        Room.remove(self, session)
        self.broadcast(session.name + ' has left the room.\r\n')

    def do_say(self, session, line):
        self.broadcast(session.name + ': ' + line + '\r\n')

    def do_look(self, session, line):
        session.push('The following are in this room: \r\n')
        for other in self.sessions:
            session.push(other.name + '\r\n')

    def do_who(self, session, line):
        session.push('The following are logged in: \r\n')
        for name in self.server.users:
            session.push(name + '\r\n')       

class LogoutRoom(Room):
    def add(self, session):
        try: 
            del self.server.user[session.name]
        except KeyError: 
            pass

class ChatSession(async_chat):
    """
    A class that takes care of a connection between the server and a single user.
    """
    def __init__(self, server, sock):
        # standard setup tasks:
        super().__init__(sock)
        self.server = server
        self.set_terminator("\r\n")
        self.data = []
        self.name = None
        self.enter(LoginRoom(server))
    
    def enter(self, room):
        try: cur = self.room
        except AttributeError: pass
        else: cur.remove(self)
        self.room = room
        room.add(self)

    def collect_incoming_data(self, data):
        self.data.append(data)
    
    def found_terminator(self):
        """
        If a terminator is found, that means a full line has been read.
        Broadcast it to everyone.
        """
        line = ''.join(self.data)
        self.data = []
        try: self.room.handle(self, line)
        except EndSession: self.handle_close()
    
    def handle_close(self):
        async_chat.handle_close(self)
        self.enter(LogoutRoom(self.server))

class ChatServer(dispatcher):
    """
    A class that recieves connections and spawns individual sessions.
    It also handles broadcasts to these sessions.
    """
    def __init__(self, port, name):
        super().__init__
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('', port))
        self.listen(5)
        self.name = name
        self.users = {}
        self.main_room = ChatRoom(self)
    
    def handle_accept(self):
        conn, addr = self.accept()
        ChatSession(self, conn)

if __name__ == '__main__':
    s = ChatServer(PORT, NAME)
    try: asyncore.loop()
    except KeyboardInterrupt: print()
        