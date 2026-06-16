#! /usr/bin/env python3
import asyncio
import os
from dataclasses import dataclass
from enum import Enum, auto
from io import BytesIO

import discord
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

SECONDS_THRESHOLD = 30

BAD_WORD_WARN_THRESHOLD_INCL = 1
BAD_WORD_BAN_THRESHOLD_INCL = 2

MSG_WARM_THRESHOLD_INCL = 3
MSG_BAN_THRESHOLD_INCL = 4

MEDIA_WARN_THRESHOLD_INCL = 2
MEDIA_BAN_THRESHOLD_INCL = 3

BAD_WORDS = ('@everyone', '@here')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@dataclass
class ChannelPost:
    channel_id: int
    author_id: int
    timestamp: float
    media_tuple: tuple[int, int, int] | None
    contains_bad_word: bool


class ModAction(Enum):
    NOTHING = auto()
    WARN = auto()
    BAN = auto()


def count_links(message: discord.Message) -> int:
    return message.content.count('https://') + message.content.count('http://')


def is_exempt(message: discord.Message) -> bool:
    roles = [r.name for r in message.author.roles]
    return 'Administrator' in roles or 'Mod' in roles


def to_media_tuple(message: discord.Message) -> tuple[int, int, int] | None:
    media_tuple = (count_links(message), len(message.attachments), len(message.embeds))
    return media_tuple if any(media_tuple) else None


class RecentPosts:
    def __init__(self):
        self.recent_posts = []
        self.lock = asyncio.Lock()

    async def get_mod_action(self, message: discord.Message) -> tuple[ModAction, str]:
        async with self.lock:
            channel_id = message.channel.id
            author_id = message.author.id
            now = message.created_at.timestamp()
            limit = now - SECONDS_THRESHOLD
            self.recent_posts = [p for p in self.recent_posts if p.timestamp > limit]
            if is_exempt(message):
                return ModAction.NOTHING, ""
            media_tuple = to_media_tuple(message)
            contains_bad_word = any(w in message.content for w in BAD_WORDS)
            self.recent_posts.append(ChannelPost(
                channel_id=channel_id,
                author_id=author_id,
                timestamp=now,
                media_tuple=media_tuple,
                contains_bad_word=contains_bad_word,
            ))
            posts_by_author = [p for p in self.recent_posts if p.author_id == author_id]
            bad_words_count = len({p for p in posts_by_author if p.contains_bad_word})
            same_media_tuple_count = len(
                [p for p in posts_by_author if p.media_tuple == media_tuple]) if media_tuple else 0
            recent_channels_count = len({p.channel_id for p in posts_by_author})

            if same_media_tuple_count >= MEDIA_BAN_THRESHOLD_INCL:
                return ModAction.BAN, f"Same media types in {same_media_tuple_count}/{MEDIA_BAN_THRESHOLD_INCL} messages within {SECONDS_THRESHOLD} seconds"
            if recent_channels_count >= MSG_BAN_THRESHOLD_INCL:
                return ModAction.BAN, f"Posted in {recent_channels_count}/{MSG_BAN_THRESHOLD_INCL} channels within {SECONDS_THRESHOLD} seconds"
            if bad_words_count >= BAD_WORD_BAN_THRESHOLD_INCL:
                return ModAction.BAN, f"Posted {bad_words_count}/{BAD_WORD_BAN_THRESHOLD_INCL} bad words within {SECONDS_THRESHOLD} seconds"

            if same_media_tuple_count >= MEDIA_WARN_THRESHOLD_INCL:
                return ModAction.WARN, "Slow down with your posting or you will get banned"
            if recent_channels_count >= MSG_WARM_THRESHOLD_INCL:
                return ModAction.WARN, "Slow down with your posting or you will get banned"
            if bad_words_count >= BAD_WORD_WARN_THRESHOLD_INCL:
                return ModAction.WARN, "Do not try to tag this many people you silly goose. It does not work, and you will get banned if you try again."

            return ModAction.NOTHING, ""


RECENT_POSTS = RecentPosts()


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    guild_list = '\n'.join([f'{guild.name}(id: {guild.id})' for guild in client.guilds])
    print(f'{client.user} is connected to the following guilds:\n{guild_list}')


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    mod_action, reason = await RECENT_POSTS.get_mod_action(message)
    if mod_action == ModAction.NOTHING:
        return
    await send_log_message(message, mod_action, reason)
    if mod_action == ModAction.WARN:
        await message.reply(reason)
    if mod_action == ModAction.BAN:
        await message.author.ban(reason=reason, delete_message_seconds=120)


def attachments_to_files(attachments: list[discord.Attachment]) -> list[discord.File]:
    files = []
    for attachment in attachments:
        response = requests.get(attachment.url)
        if response.status_code != 200:
            continue
        content = BytesIO(response.content)
        files.append(discord.File(content, attachment.filename))
    return files


async def send_log_message(message: discord.Message, mod_action: ModAction, reason: str):
    escaped_message = message.content.replace('```', '` ` `')
    verb = 'Banning' if mod_action == ModAction.BAN else 'Warning'
    log_msg = f'{verb} `{message.author.name}` (<@{message.author.id}>):\n{reason}\n\n```\n{escaped_message}\n```'
    files = attachments_to_files(message.attachments)
    print(f'[{message.created_at}] {message.guild.name=} {log_msg}')
    for channel in message.guild.text_channels:
        if channel.name in ('actual-log', 'alerta'):
            await channel.send(log_msg, files=files, embeds=message.embeds)


def main():
    client.run(TOKEN)


if __name__ == '__main__':
    main()
