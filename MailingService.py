from collections import deque
from threading import Lock
from socket import timeout

import MailingResponses

__author__ = 'ericmuxagata'


HELO        =   "HELO"
MAIL_FROM   =   "MAIL FROM"
RCPT_TO     =   "RCPT TO"
DATA        =   "DATA"

SMTP_COMMANDS = [HELO, MAIL_FROM, RCPT_TO, DATA]

# enum to keep track of the state of the communication.
class ServerState:
    EXP_HELO        = 1
    EXP_MAIL_FROM   = 2
    EXP_RCPT_TO     = 3
    FETCH_DATA     = 4
    CLOSE_CONNECTION  = 5

# Mail labels.
mail_number_lock = Lock()
mail_number = 1

#Maximum timeout
MAX_TIMEOUT = 10.0

#Payload size expected from socket.
PAYLOAD_SIZE = 500
LINE_ENDING = "\r\n"

## Handles all the mailing logic required by the server.
class MailingService:
    def __init__(self, client_socket):
        global mail_number

        self.socket = client_socket
        self.socket.settimeout(MAX_TIMEOUT)

        #Stores all the lines read so far from the client.
        self.msg_queue = deque([])
        self.msg_buffer = ""

        self.state = ServerState.EXP_HELO
        with mail_number_lock:
            self.mail_number = mail_number
            mail_number += 1

        self.hostname = ""

    def handle_mail_request(self):
        self.__send_synack()

        while self.state != ServerState.CLOSE_CONNECTION:
            msg = self.__recv_msg()
            print msg

            if self.state == ServerState.EXP_HELO:
                self.__expect_helo(msg)

            if self.state == ServerState.EXP_MAIL_FROM:
                self.__expect_mail_from(msg)

            if self.state == ServerState.EXP_RCPT_TO:
                self.__expect_rcpt_to(msg)

            if self.state == ServerState.FETCH_DATA:
                self.__expect_data(msg)



        print "Closing connection %d" % self.mail_number
        self.socket.close()

    def __expect_helo(self, message):
        msg = message.strip().split()
        if not msg:
            self.__send_msg(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        cmd = msg[0]
        if cmd not in SMTP_COMMANDS:
            self.__send_msg(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        if cmd != HELO:
            self.__send_response(MailingResponses.ERROR_MISPLACED_CMD, "need HELO command")
            return
            
        if len(msg) == 1:
            self.__send_msg(MailingResponses.ERROR_PROPER_SYNTAX)
            return

        hostname = msg[1]
        if not hostname:
            self.__send_msg(MailingResponses.ERROR_PROPER_SYNTAX)
            return

        self.hostname = hostname
        self.state = ServerState.EXP_MAIL_FROM
        self.__send_helo_ack()


    def __expect_mail_from(self, message):
        self.state = ServerState.EXP_RCPT_TO


    def __expect_rcpt_to(self, message):
        self.state = ServerState.FETCH_DATA


    def __expect_data(self, message):
        #self.state = ServerState.CLOSE_CONNECTION
        pass


    def __send_response(self, code, feedback):
        msg = MailingResponses.msg_for_code(code, feedback)
        self.__send_msg(msg)

    def __send_synack(self):
        msg = MailingResponses.msg_synack()
        self.__send_msg(msg)

    def __send_helo_ack(self):
        msg = MailingResponses.msg_helo_ack()
        self.__send_msg(msg)

    # Block to retrieve a message from the client.
    # - First checks the msg_queue for any old message that could be retrieved, o.w tries reading more;
    # - If it gets an exact number of lines, enqueues all of them in the msg_queue expect the first one;
    # - If it gets more than one line and a partial one, enqueues all but the first and the last,
    #   keeping the last to be completed in the next call;
    # - If not enough data is read for the server to respond appropriately, it blocks until it gets more;
    def __recv_msg(self):

        #Check msg queue.
        if len(self.msg_queue):
            return self.msg_queue.popleft()

        #Read from socket.
        while True:
            try:
                msg = self.socket.recv(PAYLOAD_SIZE)
                if not msg:
                    self.state = ServerState.CLOSE_CONNECTION
                    return None

                self.msg_buffer += msg
                msg_lines = self.msg_buffer.split(LINE_ENDING)

                # Return if enough data is read.
                if len(msg_lines) > 1:
                    self.msg_buffer = msg_lines[-1]

                    recv_msg = msg_lines[0]
                    msg_lines = msg_lines[1:-1]
                    if msg_lines:
                        self.msg_queue.extend(msg_lines)

                    return recv_msg
            except timeout:
                self.state = ServerState.CLOSE_CONNECTION
                return None

    def __send_msg(self, msg):
        self.socket.send(msg.encode('utf-8'))



