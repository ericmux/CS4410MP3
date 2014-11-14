__author__ = 'ericmuxagata'
__netid__ = 'eg445'


LINE_ENDING = "\r\n"

SYNACK = 220
OK  = 250

DATA_MODE = 354


ERROR_UNRECOGNIZED_CMD  = 500
ERROR_PROPER_SYNTAX     = 501
ERROR_MISPLACED_CMD     = 503
ERROR_BAD_ADDRESS       = 555
ERRORS = [ERROR_UNRECOGNIZED_CMD, ERROR_PROPER_SYNTAX, ERROR_MISPLACED_CMD, ERROR_BAD_ADDRESS]

TIMEOUT = 421


MSG_SKELETON = "{0} {1}"


def msg_synack():
    msg_body = __netid__ + " SMTP CS4410MP3" + LINE_ENDING
    return MSG_SKELETON.format(str(SYNACK), msg_body)

def msg_helo_ack():
    msg_body = __netid__ + LINE_ENDING
    return MSG_SKELETON.format(str(OK), msg_body)

def msg_for_code(code, feedback):
    msg_body = ""

    if code == OK:
        msg_body = "OK" if not feedback else "OK: " + feedback

    elif code == DATA_MODE:
        msg_body = "End data with <CR><LF>.<CR><LF>"

    elif code in ERRORS:
        if   code == ERROR_UNRECOGNIZED_CMD:
            msg_body = "Error: command not recognized"
        elif code == ERROR_PROPER_SYNTAX:
            msg_body = "Syntax:  proper syntax"
        elif code == ERROR_MISPLACED_CMD:
            msg_body = "Error: " + feedback
        elif code == ERROR_BAD_ADDRESS:
            msg_body = "<bad_email>: " + feedback

    elif code == TIMEOUT:
        msg_body = "4.4.2 %s Error: timeout exceeded" % __netid__

    return MSG_SKELETON.format(str(code), msg_body + LINE_ENDING)
