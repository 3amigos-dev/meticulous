"""
Alternative way of running meticulous via slack conversations
"""

import datetime
import logging
import os
import re
from threading import Condition

from slack_sdk.rtm_v2 import RTMClient
from slack_sdk import WebClient

from meticulous._multiworker import Interaction, multiworker_core

INPUT = 0
CONFIRMATION = 1


class SlackStateHandler(Interaction):
    """
    Records the state to await user responses
    """

    def __init__(self):
        self.alive = False
        self.started_at = datetime.datetime.min
        self.condition = Condition()
        self.await_key = None
        self.response_val = None
        self.messages = []

    def join_messages(self, message):
        self.messages.append(message)
        message = "\n".join(self.messages)
        del self.messages[:]
        return message

    def run(self, target):
        """
        Perform processing
        """
        self.started_at = datetime.datetime.now()
        self.alive = True
        while self.alive:
            multiworker_core(self, target)

    def stop(self):
        """
        Gracefully stop processing
        """
        self.alive = False
        self.started_at = datetime.datetime.min

    def get_input(self, message):
        message = self.join_messages(message)
        return self.get_await(Input(message))

    def make_choice(self, choices, message="Please make a selection."):
        message = self.join_messages(message)
        return self.get_await(Choice(choices, message))

    def check_quit(self, controller):
        return controller.tasks_empty()

    def get_confirmation(self, message="Do you want to continue", defaultval=True):
        message = self.join_messages(message)
        return self.get_await(Confirmation(message, defaultval))

    def get_await(self, key):
        """
        Work out the user response
        """
        with self.condition:
            self.response_val = None
            self.await_key = key
            while self.response_val is None:
                self.condition.wait(10)
        return self.response_val

    def receive(self, message):
        if self.await_key is None:
            MESSAGES.send_message("Message discarded {message!r} not ready yet.")
            return
        self.await_key.handle(self, message)

    def send(self, message):
        self.messages.append(message)

    def respond(self, val):
        """
        A response is chosen
        """
        with self.condition:
            self.await_key = None
            self.response_val = val
            self.condition.notify()


class Awaiter:
    """
    Waiting on some user input
    """

    def __init__(self):
        pass

    def handle(self, state, message):
        """
        Handle slack reposnse
        """
        raise NotImplementedError()


class Confirmation(Awaiter):
    """
    Yes/No
    """

    def __init__(self, message, defaultval):
        super().__init__()
        self.defaultval = defaultval
        MESSAGES.send_message(message)

    def handle(self, state, message):
        """
        Handle reply
        """
        umessage = message.upper()
        if umessage not in ("Y", "N"):
            MESSAGES.send_message(f"Unknown response {message!r} is not Y or N")
            return
        state.respond(umessage == "Y")


class Input(Awaiter):
    """
    Text Input
    """

    def __init__(self, message):
        super().__init__()
        MESSAGES.send_message(message)

    def handle(self, state, message):
        """
        Handle reply
        """
        state.respond(message)


class Choice(Awaiter):
    """
    Selection from choices
    """

    def __init__(self, choices, message):
        super().__init__()
        options = list(enumerate(sorted(choices.keys())))
        self.choices = {index: choices[txt] for index, txt in options}
        option_message = "\n".join(
            f"{index}. {txt}"
            for index, txt in (
                (indx, text.split(") ", 1)[-1]) for indx, text in options
            )
        )
        MESSAGES.send_message(f"{message}\n\n\n\n\n\n{option_message}")

    def handle(self, state, message):
        """
        Handle reply
        """
        try:
            state.respond(self.choices.get(int(message)))
        except (IndexError, ValueError):
            MESSAGES.send_message(f"Unknown response {message!r} not in choices")
            return


class SlackMessageHandler:
    def __init__(self):
        self.client = None
        self.rtm_client = None
        self.channel = None

    def start(self):
        slack_token = os.environ["SLACK_METICULOUS_TOKEN"]
        self.channel = os.environ["SLACK_METICULOUS_CHANNEL"]
        self.client = WebClient(token=slack_token)
        self.rtm_client = RTMClient(token=slack_token)

        @self.rtm_client.on("message")
        def handler(client, event):
            STATE.receive(event["text"])

        self.rtm_client.connect()
        self.send_message("Meticulous started.")

    def send_message(self, text):
        if not text:
            return
        self.client.api_call(
            "chat.postMessage",
            params={
                "channel": self.channel,
                "as_user": True,
                "text": "\n".join(
                    self.replace_ansi(self.replace_slack_formatting(line.rstrip("\n")))
                    for line in text.splitlines()
                ),
            },
        )

    @staticmethod
    def replace_slack_formatting(line):
        re1 = re.compile(r"[*_~`]")
        for r in [re1]:
            line = r.sub(".", line)
        return line

    @staticmethod
    def replace_ansi(line):
        re1 = re.compile(r"\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]")
        re2 = re.compile(r"\x1b[PX^_].*?\x1b\\")
        re3 = re.compile(r"\x1b\][^\a]*(?:\a|\x1b\\)")
        re4 = re.compile(r"\x1b[\[\]A-Z\\^_@]")
        re5 = re.compile(r"[\x00-\x1f\x7f-\x9f\xad]+")
        for r in [re1, re2, re3, re4, re5]:
            line = r.sub("*", line)
        return line


STATE = SlackStateHandler()
MESSAGES = SlackMessageHandler()


def main(target):
    """
    Alternative way of running meticulous via slack conversations
    """
    logging.basicConfig(level=logging.WARNING)
    logging.debug("running slack...")
    MESSAGES.start()
    STATE.run(target)
