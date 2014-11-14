import re

from threading import Lock

from collections import deque
from socket import timeout

import MailingResponses, MailWriter

__author__ = 'ericmuxagata'


HELO        =   "HELO"
MAIL_FROM   =   "MAIL FROM"
RCPT_TO     =   "RCPT TO"
DATA        =   "DATA"

SMTP_COMMANDS = [HELO, MAIL_FROM, RCPT_TO, DATA]

NEED_COMMAND_SKELETON = "need {0} command"

# enum to keep track of the state of the communication.
class ServerState:
    EXP_HELO                = 1
    EXP_MAIL_FROM           = 2
    EXP_RCPT_TO             = 3
    EXP_DATA_OR_RECPT_TO    = 4
    FETCH_DATA              = 5
    CLOSE_CONNECTION        = 6

#Maximum timeout
MAX_TIMEOUT = 10.0

#Payload size expected from socket.
PAYLOAD_SIZE = 500
LINE_ENDING = "\r\n"
EOF_LINE = "."

##Connection labels.
conn_id = 0
conn_id_lock = Lock()

## Handles all the mailing logic required by the server.
class MailingService:
    def __init__(self, client_socket):
        global mail_number

        self.socket = client_socket
        self.socket.settimeout(MAX_TIMEOUT)

        with conn_id_lock:
            global conn_id
            conn_id += 1
            self.conn_id = conn_id

        #Stores all the lines read so far from the client.
        self.msg_queue = deque([])
        self.msg_buffer = ""

        self.state = ServerState.EXP_HELO

        self.hostname   = ""
        self.send_addr  = ""
        self.recpt_addrs = []
        self.data = []

    def handle_mail_request(self):
        self.__send_synack()

        while self.state != ServerState.CLOSE_CONNECTION:
            msg = self.__recv_msg()
            print msg

            if self.state == ServerState.EXP_HELO:
                self.__expect_helo(msg)
                continue

            if self.state == ServerState.EXP_MAIL_FROM:
                self.__expect_mail_from(msg)
                continue

            if self.state == ServerState.EXP_RCPT_TO:
                self.__expect_rcpt_to(msg)
                continue

            if self.state == ServerState.EXP_DATA_OR_RECPT_TO:
                self.__expect_data_or_rcpt_to(msg)
                continue

            if self.state == ServerState.FETCH_DATA:
                self.__expect_raw_data(msg)
                continue

        print "Closing connection %d" % self.conn_id
        self.socket.close()

    def __expect_helo(self, message):
        msg = message.strip()
        if not msg:
            self.__send_msg(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        msg = msg.split()

        cmd = msg[0].upper()
        if cmd not in SMTP_COMMANDS:
            self.__send_response(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        if cmd != HELO:
            self.__send_response(MailingResponses.ERROR_MISPLACED_CMD, NEED_COMMAND_SKELETON.format(HELO))
            return

        # Discard interleaving whitespace.
        msg = filter(lambda x:x, msg)

        if len(msg) != 2:
            self.__send_response(MailingResponses.ERROR_PROPER_SYNTAX)
            return

        hostname = msg[1]
        if not hostname:
            self.__send_response(MailingResponses.ERROR_PROPER_SYNTAX)
            return

        self.hostname = hostname
        self.state = ServerState.EXP_MAIL_FROM
        self.__send_helo_ack()


    def __expect_mail_from(self, message):
        msg = message.strip()
        if not msg:
            self.__send_response(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        msg = msg.split(':')

        cmd = msg[0].upper()
        if cmd not in SMTP_COMMANDS:
            self.__send_response(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        if cmd != MAIL_FROM:
            self.__send_response(MailingResponses.ERROR_MISPLACED_CMD, NEED_COMMAND_SKELETON.format(MAIL_FROM))
            return

        # Discard interleaving whitespace.
        msg = filter(lambda x:x, msg)

        if len(msg) != 2:
            self.__send_response(MailingResponses.ERROR_PROPER_SYNTAX)
            return

        addr = msg[1].strip()
        if re.findall('\s+', addr):
            self.__send_response(MailingResponses.ERROR_BAD_ADDRESS, "Sender address rejected")
            return

        self.send_addr = addr
        self.state = ServerState.EXP_RCPT_TO
        self.__send_response(MailingResponses.OK)


    def __expect_rcpt_to(self, message):
        msg = message.strip()
        if not msg:
            self.__send_response(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        msg = msg.split(':')

        cmd = msg[0].upper()
        if cmd not in SMTP_COMMANDS:
            self.__send_response(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        if cmd != RCPT_TO:
            self.__send_response(MailingResponses.ERROR_MISPLACED_CMD, NEED_COMMAND_SKELETON.format(RCPT_TO))
            return

        # Discard interleaving whitespace.
        msg = filter(lambda x:x, msg)

        if len(msg) != 2:
            self.__send_response(MailingResponses.ERROR_PROPER_SYNTAX)
            return

        addr = msg[1].strip()
        if re.findall('\s+', addr):
            self.__send_response(MailingResponses.ERROR_BAD_ADDRESS, "Recipient address invalid")
            return

        self.recpt_addrs.append(addr)
        self.state = ServerState.EXP_DATA_OR_RECPT_TO
        self.__send_response(MailingResponses.OK)


    def __expect_data_or_rcpt_to(self, message):
        msg = message.strip()
        if not msg:
            self.__send_response(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        msg = msg.split(':')

        cmd = msg[0].upper()
        if cmd not in SMTP_COMMANDS:
            self.__send_response(MailingResponses.ERROR_UNRECOGNIZED_CMD)
            return

        if cmd != RCPT_TO and cmd != DATA:
            self.__send_response(MailingResponses.ERROR_MISPLACED_CMD, NEED_COMMAND_SKELETON.format(DATA))
            return

        # Discard interleaving whitespace.
        msg = filter(lambda x:x, msg)

        # Extra recipient, add to recpt_addrs.
        if cmd == RCPT_TO:
            if len(msg) != 2:
                self.__send_response(MailingResponses.ERROR_PROPER_SYNTAX)
                return

            addr = msg[1].strip()
            if re.findall('\s+', addr):
                self.__send_response(MailingResponses.ERROR_BAD_ADDRESS, "Recipient address invalid")
                return

            self.recpt_addrs.append(addr)
            self.__send_response(MailingResponses.OK)
            return

        # Data command, handle.
        if len(msg) != 1:
            self.__send_response(MailingResponses.ERROR_PROPER_SYNTAX)
            return

        self.state = ServerState.FETCH_DATA
        self.__send_response(MailingResponses.DATA_MODE)

    def __expect_raw_data(self, message):
        msg = message

        if msg == EOF_LINE:
            mail_number = self.__write_mail()
            self.__send_response(MailingResponses.OK, "Delivered message %d" % mail_number)
            self.state = ServerState.EXP_MAIL_FROM
            self.send_addr , self.recpt_addrs, self.data = "", [], []
            return

        self.data.append(msg)


    def __send_response(self, code, feedback=''):
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
            except IOError:
                self.state = ServerState.CLOSE_CONNECTION
                return

    def __send_msg(self, msg):
        try:
            self.socket.send(msg.encode('utf-8'))
        except IOError:
                self.state = ServerState.CLOSE_CONNECTION
                return


    def __write_mail(self):
        mail_number = MailWriter.write_mail(self.hostname, MailingResponses.__netid__, self.send_addr, self.recpt_addrs, "\n".join(self.data))
        return mail_number