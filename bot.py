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

DELETE_WINDOW = 5 * 60
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
    message: discord.Message


@dataclass
class BannedAuthor:
    author_id: int
    timestamp: float


class ModAction(Enum):
    NOTHING = auto()
    WARN = auto()
    BAN = auto()
    DELETE = auto()


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
        self.banned_author_ids = []
        self.lock = asyncio.Lock()

    async def get_mod_action(self, message: discord.Message) -> tuple[ModAction, str, list[ChannelPost]]:
        async with self.lock:
            channel_id = message.channel.id
            author_id = message.author.id
            now = message.created_at.timestamp()
            purge_limit = now - DELETE_WINDOW
            limit = now - SECONDS_THRESHOLD
            self.banned_author_ids = [b for b in self.banned_author_ids if b.timestamp > purge_limit]
            self.recent_posts = [p for p in self.recent_posts if p.timestamp > purge_limit]
            if is_exempt(message):
                return ModAction.NOTHING, "", []
            media_tuple = to_media_tuple(message)
            contains_bad_word = any(w in message.content for w in BAD_WORDS)
            self.recent_posts.append(ChannelPost(
                channel_id=channel_id,
                author_id=author_id,
                timestamp=now,
                media_tuple=media_tuple,
                contains_bad_word=contains_bad_word,
                message=message,
            ))
            all_posts_by_author = [p for p in self.recent_posts if p.author_id == author_id]
            posts_by_author = [p for p in all_posts_by_author if p.timestamp > limit]
            bad_words_count = len({p for p in posts_by_author if p.contains_bad_word})
            same_media_tuple_count = len(
                [p for p in posts_by_author if p.media_tuple == media_tuple]) if media_tuple else 0
            recent_channels_count = len({p.channel_id for p in posts_by_author})

            if author_id in {a.author_id for a in self.banned_author_ids}:
                return ModAction.DELETE, f"Deleting message by banned author {message.author.name}", all_posts_by_author

            if same_media_tuple_count >= MEDIA_BAN_THRESHOLD_INCL:
                self.banned_author_ids.append(BannedAuthor(author_id=author_id, timestamp=now))
                return ModAction.BAN, f"Same media types in {same_media_tuple_count}/{MEDIA_BAN_THRESHOLD_INCL} messages within {SECONDS_THRESHOLD} seconds", all_posts_by_author
            if recent_channels_count >= MSG_BAN_THRESHOLD_INCL:
                self.banned_author_ids.append(BannedAuthor(author_id=author_id, timestamp=now))
                return ModAction.BAN, f"Posted in {recent_channels_count}/{MSG_BAN_THRESHOLD_INCL} channels within {SECONDS_THRESHOLD} seconds", all_posts_by_author
            if bad_words_count >= BAD_WORD_BAN_THRESHOLD_INCL:
                self.banned_author_ids.append(BannedAuthor(author_id=author_id, timestamp=now))
                return ModAction.BAN, f"Posted {bad_words_count}/{BAD_WORD_BAN_THRESHOLD_INCL} bad words within {SECONDS_THRESHOLD} seconds", all_posts_by_author

            if same_media_tuple_count >= MEDIA_WARN_THRESHOLD_INCL:
                return ModAction.WARN, "Slow down with your posting or you will get banned", all_posts_by_author
            if recent_channels_count >= MSG_WARM_THRESHOLD_INCL:
                return ModAction.WARN, "Slow down with your posting or you will get banned", all_posts_by_author
            if bad_words_count >= BAD_WORD_WARN_THRESHOLD_INCL:
                return ModAction.WARN, "Do not try to tag this many people you silly goose. It does not work, and you will get banned if you try again.", all_posts_by_author

            return ModAction.NOTHING, "", []


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
    mod_action, reason, all_posts_by_author = await RECENT_POSTS.get_mod_action(message)
    if mod_action == ModAction.NOTHING:
        return
    await send_log_message(message, mod_action, reason, all_posts_by_author)
    if mod_action == ModAction.DELETE:
        await message.delete(delay=1)  # delay so we don't have to deal with error handling
    if mod_action == ModAction.WARN:
        await message.reply(reason)
    if mod_action == ModAction.BAN:
        await message.author.ban(reason=reason, delete_message_seconds=120)
        for post in all_posts_by_author:
            await post.message.delete(delay=1)  # delay so we don't have to deal with error handling


def attachments_to_files(attachments: list[discord.Attachment]) -> list[discord.File]:
    files = []
    for attachment in attachments:
        response = requests.get(attachment.url)
        if response.status_code != 200:
            continue
        content = BytesIO(response.content)
        files.append(discord.File(content, attachment.filename))
    return files


async def send_log_message(message: discord.Message, mod_action: ModAction, reason: str, all_posts_by_author: list[ChannelPost]):
    escaped_message = message.content.replace('```', '` ` `')
    verb = 'Banning' if mod_action == ModAction.BAN else 'Warning'
    urls = [p.message.jump_url for p in all_posts_by_author]
    recent_messages = "" if mod_action == ModAction.BAN else "Recent messages:\n" + "\n".join(urls)
    log_msg = f'{verb} `{message.author.name}` (<@{message.author.id}>):\n{reason}\n{recent_messages}\n```\n{escaped_message}\n```'
    files = attachments_to_files(message.attachments)
    print(f'[{message.created_at}] {message.guild.name=} {log_msg}')
    for channel in message.guild.text_channels:
        if channel.name in ('actual-log', 'alerta'):
            await channel.send(log_msg, files=files, embeds=message.embeds)


def main():
    client.run(TOKEN)


if __name__ == '__main__':
    main()
