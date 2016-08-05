import discord
import asyncio
import pendulum
from pytz import all_timezones

import plugins
from pcbot import Config, Annotate, get_member


time_cfg = Config("time", data=dict(countdown={}, timezone={}))
dt_format = "%A, %d %B %Y %H:%M:%S"


@plugins.argument()
def tz_arg(timezone: str):
    """ Get timezone from a string. """
    for tz in all_timezones:
        if tz.lower().endswith(timezone.lower()):
            return tz
    return None


def reverse_gmt(timezone: str):
    """ POSIX is stupid so these are reversed. """
    if "+" in timezone:
        timezone = timezone.replace("+", "-")
    elif "-" in timezone:
        timezone = timezone.replace("-", "+")

    return timezone


@asyncio.coroutine
def init_dt(client: discord.Client, message: discord.Message, time: str, timezone: str):
    """ Setup the datetime and timezone properly. """
    timezone = reverse_gmt(timezone)

    try:
        dt = pendulum.parse(time, tz=timezone)
    except ValueError:
        yield from client.say(message, "Time format not recognized.")
        return

    return dt, timezone


def format_when(dt: pendulum.Pendulum, timezone: str="UTC"):
    """ Format when something will happen"""
    now = pendulum.utcnow()

    diff = dt - now
    major_diff = dt.diff_for_humans(absolute=True)
    detailed_diff = diff.in_words().replace("-", "")

    return "`{time} {tz}` {pronoun} **{major}{diff}{pronoun2}**.".format(
        time=dt.format(dt_format),
        tz=timezone,
        pronoun="is in" if dt > now else "was",
        major="~" + major_diff + "** / **" if major_diff not in detailed_diff else "",
        diff=detailed_diff,
        pronoun2=" ago" if dt < now else ""
    )


@plugins.command(aliases="timezone")
def when(client: discord.Client, message: discord.Message, *time, timezone: tz_arg="UTC"):
    """ Convert time from specified timezone or UTC to formatted string of e.g.
    `2 hours from now`. """
    timezone_name = timezone

    if time:
        dt, timezone = yield from init_dt(client, message, " ".join(time), timezone)

        yield from client.say(message, format_when(dt, timezone_name))
    else:
        timezone = reverse_gmt(timezone)
        dt = pendulum.now(tz=timezone)

        yield from client.say(message, "`{} {}` is **UTC{}{}**.".format(
            dt.format(dt_format), timezone_name,
            "-" if dt.offset_hours < 0 else ("+" if dt.offset_hours > 0 else ""),
            abs(dt.offset_hours) if dt.offset_hours else "",
        ))


@plugins.argument()
def tag_arg(tag: str):
    """ A countdown tag. """
    return tag.lower().replace(" ", "")


@plugins.command(aliases="cd downcount")
def countdown(client: discord.Client, message: discord.Message, tag: Annotate.Content):
    """ Display a countdown with the specified tag. """
    tag = tag_arg(tag)
    assert tag in time_cfg.data["countdown"], "Countdown with tag `{}` does not exist.".format(tag)

    cd = time_cfg.data["countdown"][tag]
    dt = pendulum.parse(cd["time"], tz=cd["tz"])
    timezone_name = cd["tz_name"]

    yield from client.say(message, format_when(dt, timezone_name))


@countdown.command(aliases="add", pos_check=True)
def create(client: discord.Client, message: discord.Message, tag: tag_arg, *time, timezone: tz_arg="UTC"):
    """ Create a countdown with the specified tag, using the same format as `{pre}when`. """
    assert tag not in time_cfg.data["countdown"], "Countdown with tag `{}` already exists.".format(tag)

    timezone_name = timezone
    dt, timezone = yield from init_dt(client, message, " ".join(time), timezone)

    assert (dt - pendulum.utcnow()).seconds > 0, "A countdown has to be set in the future."

    time_cfg.data["countdown"][tag] = dict(time=dt.to_datetime_string(), tz=timezone, tz_name=timezone_name,
                                           author=message.author.id)
    time_cfg.save()
    yield from client.say(message, "Added countdown with tag `{}`.".format(tag))


@countdown.command(aliases="remove")
def delete(client: discord.Client, message: discord.Message, tag: Annotate.Content):
    """ Remove a countdown with the specified tag. You need to be the author of a tag
    in order to remove it. """
    tag = tag_arg(tag)
    assert tag in time_cfg.data["countdown"], "Countdown with tag `{}` does not exist.".format(tag)

    author_id = time_cfg.data["countdown"][tag]["author"]
    assert message.author.id == author_id, "You are not the author of this tag ({}).".format(
        getattr(get_member(client, author_id), "name", None) or "~~Unknown~~")

    del time_cfg.data["countdown"][tag]
    time_cfg.save()
    yield from client.say(message, "Countdown with tag `{}` removed.".format(tag))


@countdown.command(name="list")
def cmd_list(client: discord.Client, message: discord.Message, author: Annotate.Member=None):
    """ List all countdowns or all countdowns by the specified author. """
    assert time_cfg.data["countdown"], "There are no countdowns created."

    if author:
        tags = (tag for tag, value in time_cfg.data["countdown"].items() if value["author"] == author.id)
    else:
        tags = (tag for tag in time_cfg.data["countdown"].keys())

    yield from client.say(message, "**{}countdown tags**:```\n{}```".format(
        "{}'s ".format(author.name) if author else "", ", ".join(tags)))
