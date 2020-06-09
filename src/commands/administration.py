"""
administration.py  -- administration commands

This module contains commands specific to administering the bot.

Copyright (c) 2019 The Fuel Rats Mischief,
All rights reserved.

Licensed under the BSD 3-Clause License.

See LICENSE.md
"""

from ..config import setup
from ..packages.cli_manager import cli_manager
from ..packages.commands import command
from ..packages.context import Context
from ..packages.permissions import require_channel, require_permission, TECHRAT
from loguru import logger
from os import path
import src
from importlib import resources
import toml


@command("rehash")
@require_channel(message="please do this where everyone can see 😒")
@require_permission(TECHRAT, override_message="no.")
async def cmd_rehash(context: Context):
    """ rehash the hash browns. (reloads config file)"""
    logger.warning(f"config rehashing invoked by user {context.user.nickname}")
    path = cli_manager.GET_ARGUMENTS().config_file
    await context.reply(f"reloading configuration...")
    try:
        _, resulting_hash = setup(path)
    except (KeyError, ValueError) as exc:
        # emit stacktrace to logfile
        logger.exception("failed to rehash configuration.")
        # if you have access to mecha's configuration file, you have access to its logs.
        # no need to defer this to the top-level exception handler.
        await context.reply(f"unable to rehash configuration file see logfile for details.")

    else:
        # no errors, respond status OK with the first octet of the hash.
        await context.reply(f"rehashing completed successfully. ({resulting_hash[:8]}) ")


@command("version")
async def cmd_version(ctx: Context):
    """
    This function shows the current version of the bot, as represented in pyproject.toml

    Args:
        ctx (Context): Context of the command

    Returns:
        msg (str): Result of the Context::reply call
    """
    # FIXME Rather than pull the entire toml file, just pull what we need.

    try:
        # Load the TOML file if it exists
        if path.isfile("pyproject.toml"):
            toml_data = toml.load("pyproject.toml")

            # Send the version we find.  If this doesn't work, it will raise a KeyError
            return await ctx.reply("Version " + toml_data["tool"]["poetry"]["version"])
        else:
            # If we can't find the file, raise a FileNotFoundError
            raise FileNotFoundError("Toml file doesn't exist.")
    except FileNotFoundError:
        # Handle a custom log message if we can't find the file.
        logger.warning("Unable to find pyproject.toml when issuing version command")
    except KeyError:
        logger.warning("Unable to find key [\"tool\"][\"poetry\"][\"version\"] in toml when issuing version command")

    # Return a default version string.  We will only hit this if we see an exception above.
    return await ctx.reply("version ?.?.? (dirty)")
