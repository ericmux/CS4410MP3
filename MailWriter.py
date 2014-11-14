from threading import Lock
__author__ = 'ericmuxagata'
__mailbox_path__ = 'mailbox'

mailbox_lock = Lock()
mail_number = 0

TO_SKELETON = "To: {0}"
MAIL_SKELETON = """Received: from {0} by {1} (CS4410MP3)\nNumber: {2}\nFrom: {3}\n{4}\n\n{5}\n\n"""

def empty_mailbox():
    with open(__mailbox_path__, 'w'):
        pass


def write_mail(hostname, netid, send_addr, recpt_addrs, msg_body):
    to_lines = '\n'.join([TO_SKELETON.format(recpt) for recpt in recpt_addrs])

    with mailbox_lock:
        global mail_number
        mail_number += 1
        mail_text = MAIL_SKELETON.format(hostname, netid, str(mail_number), send_addr, to_lines, msg_body)
        with open(__mailbox_path__, 'a') as mbox:
            mbox.write(mail_text)
        ret_mail_number = mail_number
    return ret_mail_number
