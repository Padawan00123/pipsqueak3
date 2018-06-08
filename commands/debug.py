"""
debug.py - Debug and diagnostics commands

Provides IRC commands geared towards debugging mechasqueak itself.
This module should **NOT** be loaded in a production environment

Copyright (c) 2018 The Fuel Rats Mischief,
All rights reserved.

Licensed under the BSD 3-Clause License.

See LICENSE.md
"""
import logging

from Modules.permissions import require_permission, TECHRAT
from Modules.rat_command import Commands

log = logging.getLogger(f"mecha.{__name__}")


@require_permission(TECHRAT)
@Commands.command("debug-whois")
async def cmd_debug_whois(bot, trigger):
    data = await bot.whois(trigger.words[1])
    log.debug(data)
    await trigger.reply(f"{data}")
