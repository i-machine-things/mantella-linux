import logging
import socket
import click
from fastapi import FastAPI
import uvicorn
from src.http.routes.routeable import routeable
from src import utils

logger = utils.get_logger()


class http_server:
    """A simple http server using FastAPI. Can be started using different routes.
    """
    def __init__(self) -> None:
        self.__app = FastAPI()

        ### Deactivate the logging to console by FastAPI
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        def secho(text, file=None, nl=None, err=None, color=None, **styles):
            pass

        def echo(text, file=None, nl=None, err=None, color=None, **styles):
            pass

        click.echo = echo
        click.secho = secho
        ### End of deactivate logging

    @property
    def app(self) -> FastAPI:
        return self.__app

    def _setup_routes(self, routes: list[routeable]):
        """Sets up the provided server routes
        
        Args:
            routes (list[routeable]): The list of routes to set up
        """
        for route in routes:
            route.add_route_to_server(self.__app)
        return self.__app

    def start(self, port: int, routes: list[routeable], play_startup_sound: bool, show_debug: bool = False):
        """Starts the server and sets up the provided routes

        Args:
            routes (list[routeable]): The list of routes to start
            show_debug (bool, optional): should debug output be shown
        """
        self._setup_routes(routes)

        if play_startup_sound:
            utils.play_mantella_ready_sound()
        
        logger.log(24, '\nConversations not starting when you select an NPC? See here:')
        logger.log(25, 'https://art-from-the-machine.github.io/Mantella/pages/issues_qna')
        logger.log(24, '\nWaiting for player to select an NPC...')
    
        # Bind a genuine dual-stack socket (both IPv4 and IPv6 loopback) ourselves:
        # on this system "localhost" resolves to ::1 (IPv6) before 127.0.0.1, and
        # the SKSE_HTTP plugin (running under Wine) uses the literal string
        # "localhost" for some of its requests while using "127.0.0.1" for others.
        # uvicorn's host="::" alone enables IPV6_V6ONLY by default here, which
        # would silently drop the 127.0.0.1 connections instead. Explicitly
        # disabling IPV6_V6ONLY gives us both on the single port the game expects.
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::", port))
        uvicorn.run(self.__app, fd=sock.fileno())
