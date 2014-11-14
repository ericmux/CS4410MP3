import MailWriter
from MailingService import MailingService
from threading import Thread, Condition, Lock

POOL_SIZE = 32

class MailingThreadPool:
    def __init__(self):
        self.lock = Lock()
        self.available_threads_cv = Condition(self.lock)

        self.pool = [MailingThread(self, i) for i in xrange(POOL_SIZE)]

        # Keeps track of which threads can still receive requests.
        self.open_threads_stack = list(self.pool)

        # Keeps track of which threads were invoked to be run.
        self.invoked = {}
        for m_thread in self.pool:
            self.invoked[m_thread] = False

        #Condition variables for each mail service thread.
        self.invoked_thread_cv = {}
        for m_thread in self.pool:
            self.invoked_thread_cv[m_thread] = Condition(self.lock)

        # Start mailing threads so they await for requests.
        for m_thread in self.pool:
            m_thread.start()

        # Empty mailbox
        MailWriter.empty_mailbox()


    ## Checks if there are threads available to handle the client connection.
    def __available_threads(self):
        return (len(self.open_threads_stack) != 0)

    ## Used by server to hand over a new accepted client socket. Blocks if we cannot process the request yet.
    def dispatch_mail_request(self, client_socket):
        with self.lock:
            # If we cannot process the request, block so we stop the server from accepting new connections.
            while not self.__available_threads():
                self.available_threads_cv.wait()

            # Invoke a mailing thread to handle the connection.
            m_thread = self.open_threads_stack.pop()
            self.invoked[m_thread] = True
            self.invoked_thread_cv[m_thread].notify()

            # Hand over the socket to the thread.
            m_thread.client_socket = client_socket


    # Used by the mailing threads to wait for their time to shine.
    def await_mail_request(self, m_thread):
        with self.lock:
            while not self.invoked[m_thread]:
                self.invoked_thread_cv[m_thread].wait()
            self.invoked[m_thread] = False


    # Used by the mailing threads to announce their reinstated availability.
    def reopen_mail_service(self, m_thread):
        with self.lock:
            self.open_threads_stack.append(m_thread)
            self.available_threads_cv.notify()


## Acutally handles the connection to the client. Has no synchronization logic at all, as it relies on
## the thread pool for this purpose.
class MailingThread(Thread):
    def __init__(self, parent_pool, index):
        super(MailingThread, self).__init__()
        self.mailing_thread_pool = parent_pool
        self.client_socket = None
        self.index = index

    def run(self):
        while True:
            # Wait for a socket from the pool.
            self.mailing_thread_pool.await_mail_request(self)

            ## Handle mail request under the whole SMTP logic.
            mailing_service = MailingService(self.client_socket)
            mailing_service.handle_mail_request()

            # Announce availability now the connection is handled.
            self.mailing_thread_pool.reopen_mail_service(self)
