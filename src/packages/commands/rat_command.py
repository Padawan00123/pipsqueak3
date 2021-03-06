"""
rat_command.py - Handles Command registration and Command-triggering IRC events

Copyright (c) 2018 The Fuel Rat Mischief,
All rights reserved.

Licensed under the BSD 3-Clause License.

See LICENSE.md

This module is built on top of the Pydle system.

"""

import typing
from typing import Any, Callable, Tuple

import attr
import prometheus_client
import psycopg2
import pyparsing
from loguru import logger
from prometheus_async.aio import time as aio_time
from pyparsing import Word, Suppress, alphanums, alphas, ZeroOrMore

from src.packages.permissions import Permission
from src.packages.rules.rules import get_rule
from ..context import Context
from ..ratmama.ratmama_parser import handle_ratmama_announcement

TRIGGER_TIME = prometheus_client.Histogram(
    namespace="commands",
    name="trigger",
    unit="seconds",
    documentation="time spent in trigger"
)
TRIGGER_MISS = prometheus_client.Counter(
    namespace="commands",
    name="trigger_miss",
    documentation="total times trigger couldn't handle a message"
)
COMMAND_TIME = prometheus_client.Histogram(
    namespace="commands",
    name="in_command",
    unit="seconds",
    documentation="time spent triggering commands"
)
FACT_TIME = prometheus_client.Histogram(
    namespace="commands",
    name="in_fact",
    unit="seconds",
    documentation="time spent triggering facts"
)
TIME_IN_COMMAND = prometheus_client.Histogram(
    namespace="commands",
    name="time_in",
    unit="seconds",
    documentation="time spent triggering commands",
    labelnames=['command']
)


# set the logger for rat_command


class CommandException(Exception):
    """
    base Command Exception
    """


class InvalidCommandException(CommandException):
    """
    invoked command failed validation
    """


class NameCollisionException(CommandException):
    """
    Someone attempted to register a command already registered.
    """


_registered_commands = {}  # pylint: disable=invalid-name


def truthy_validator(inst, attribute, value):
    if not value:
        raise ValueError(value)


@attr.dataclass
class Command:
    underlying: typing.Callable = attr.ib(validator=attr.validators.is_callable())

    aliases: typing.Tuple[str] = attr.ib(validator=attr.validators.and_(attr.validators.deep_iterable(
        member_validator=attr.validators.instance_of(str),
        iterable_validator=attr.validators.instance_of(tuple)),
        truthy_validator
    ), )
    require_permission: typing.Optional[Permission] = attr.ib(
        validator=attr.validators.optional(attr.validators.instance_of(Permission)),
        default=None
    )
    require_channel: bool = attr.ib(default=False, validator=attr.validators.instance_of(bool))
    require_direct_message: bool = attr.ib(default=False, validator=attr.validators.instance_of(bool))
    func: typing.Optional[typing.Callable] = attr.ib(default=None)

    async def __call__(self, *args, **kwargs):
        # TODO: pre-execution hooks would go here
        with TIME_IN_COMMAND.labels(command=self.aliases[0]).time():
            return await self.underlying(*args, **kwargs)


@aio_time(TRIGGER_TIME)
async def trigger(ctx) -> Any:
    """

    Args:
        ctx (Context): Invocation context

    Returns:
        result of command execution
    """

    if ctx.words_eol[0] == "":
        return  # empty message, bail out

    if ctx.prefixed:
        if ctx.words[0].casefold() in _registered_commands:
            # A regular command
            command_fun = _registered_commands[ctx.words[0].casefold()]
            extra_args = ()
            logger.debug(f"Regular command {ctx.words[0]} invoked.")
        else:
            # Might be a regular rule
            command_fun, extra_args = get_rule(ctx.words, ctx.words_eol, prefixless=False)
            if command_fun:
                logger.debug(
                    f"Rule {getattr(command_fun, '__name__', '')} matching {ctx.words[0]} found.")
            else:
                logger.debug(f"Could not find command or rule for {ctx.words[0]}.")
    else:
        # Might still be a prefixless rule
        command_fun, extra_args = get_rule(ctx.words, ctx.words_eol, prefixless=True)
        if command_fun:
            logger.debug(
                f"Prefixless rule {getattr(command_fun, '__name__', '')} matching {ctx.words[0]} "
                f"found.")

    if ctx.words_eol[0].startswith("Incoming Client:"):
        command_fun = handle_ratmama_announcement

    if command_fun:
        return await command_fun(ctx, *extra_args)

    # neither a rule nor a command, possibly a fact
    result = False
    if ctx.prefixed:
        result = await handle_fact(ctx)
    if not result:
        TRIGGER_MISS.inc()
        logger.debug(f"Ignoring message '{ctx.words_eol[0]}'. Not a command or rule.")


@aio_time(FACT_TIME)
async def handle_fact(context: Context):
    """
    Handles potential facts
    """
    logger.trace("entering fact handler")
    pattern = (
            Word(alphanums).setResultsName("name")
            + pyparsing.Optional(Suppress('-') + Word(alphas).setResultsName("lang"))
            + ZeroOrMore(Word(alphanums + '_[]|?.<>{}-=')).setResultsName("subjects")
    )
    logger.debug("parsing {!r} for facts...", context.words_eol[0])
    try:
        result = pattern.parseString(context.words_eol[0])
    except pyparsing.ParseException:
        logger.debug("failed to parse {!r} as a fact", context.words_eol[0])
        return

    fact = result.name
    lang = result.lang if result.lang else 'en'
    users = result.subjects.asList() if result.subjects else []
    try:
        # don't do anything if the fact doesn't exist
        if not await context.bot.fact_manager.exists(fact.casefold(), lang.casefold()):
            logger.debug("no such fact name={!r} lang={!r}", fact, lang)
            return False

        logger.debug("fact exists, retrieving and returning!")
        fact = await context.bot.fact_manager.find(fact.casefold(), lang.casefold())
        await context.reply(f"{', '.join(users)}{': ' if users else ''}{fact.message}")
        return True
    except psycopg2.Error:
        logger.exception("failed to fetch fact")
        return False


def _register(func, names: typing.Union[typing.Iterable[str], str]) -> bool:
    """
    Register a new command
    :param func: function
    :param names: names to register
    :return: success
    """
    if isinstance(names, str):
        names = [names]  # idiot proofing

    # transform commands to lowercase
    names = [name.casefold() for name in names]

    if func is None or not callable(func):
        # command not callable
        return False

    for alias in names:
        if alias in _registered_commands:
            # command already registered
            raise NameCollisionException(f"attempted to re-register command(s) {alias}")
        else:
            formed_dict = {alias: func}
            _registered_commands.update(formed_dict)

    return True


def command(*aliases: str, **kwargs):
    """
    Registers a command by aliases

    Args:
        *aliases ([str]): aliases to register

    """

    def real_decorator(func: Callable):
        """
        The actual commands decorator

        Args:
            func (Callable): wrapped function

        Returns:
            Callable: *func*, unmodified.
        """
        logger.debug(f"Registering command aliases: {aliases}...")

        cmd = Command(underlying=func, aliases=aliases, **kwargs)
        if not _register(cmd, aliases):
            raise InvalidCommandException("unable to register commands.")
        logger.debug(f"Registration of {aliases} completed.")

        return func

    return real_decorator
