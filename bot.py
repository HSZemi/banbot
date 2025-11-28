#! /usr/bin/env python3
import asyncio
import os
from dataclasses import dataclass

import discord
from discord import Guild, Member, User
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

SUS_ITEMS_THRESHOLD = 3
SUS_POSTS_THRESHOLD = 2
LINK_THRESHOLD = 5
CHANNEL_THRESHOLD = 5
SECONDS_THRESHOLD = 30

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@dataclass
class ChannelPost:
    channel_id: int
    author_id: int
    timestamp: float
    sus: bool
    links: int


def is_suspicious(message: discord.Message) -> bool:
    return len(message.attachments) + len(message.embeds) >= SUS_ITEMS_THRESHOLD


def count_links(message: discord.Message) -> int:
    return message.content.count('https://') + message.content.count('http://')


class RecentPosts:
    def __init__(self):
        self.recent_posts = []
        self.lock = asyncio.Lock()

    async def should_ban(self, message: discord.Message) -> bool:
        async with self.lock:
            channel_id = message.channel.id
            author_id = message.author.id
            now = message.created_at.timestamp()
            limit = now - SECONDS_THRESHOLD
            self.recent_posts = [p for p in self.recent_posts if p.timestamp > limit]
            sus = is_suspicious(message)
            links = count_links(message)
            self.recent_posts.append(ChannelPost(
                channel_id=channel_id, author_id=author_id, timestamp=now, sus=sus, links=links
            ))
            recent_channels_count = len({p.channel_id for p in self.recent_posts if p.author_id == author_id})
            too_many_channels = recent_channels_count >= CHANNEL_THRESHOLD
            too_sus = len([p for p in self.recent_posts if p.sus and p.author_id == author_id]) >= SUS_POSTS_THRESHOLD
            too_many_links = sum([p.links for p in self.recent_posts if p.author_id == author_id]) >= LINK_THRESHOLD
            return too_many_channels or too_sus or too_many_links


RECENT_POSTS = RecentPosts()

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    guild_list = '\n'.join([f'{guild.name}(id: {guild.id})' for guild in client.guilds])
    print(f'{client.user} is connected to the following guilds:\n{guild_list}')


@client.event
async def on_message(message):
    if message.author.bot:
        return
    for bad_word in ('@everyone', '@here'):
        if bad_word in message.content:
            print(f'[{message.created_at}] Banning {message.author} for {message.content=} in {message.guild=}')
            await message.author.ban(reason=f'Tried to use {bad_word}', delete_message_seconds=120)
            await send_naughty_word_log_message(message.author, message.content, message.guild)
            return
    if await RECENT_POSTS.should_ban(message):
        reason = f'Recent posts have been deemed banworthy by our robot overlords'
        await message.author.ban(reason=reason, delete_message_seconds=120)
        await send_rate_limit_log_message(message.author, message.guild)


async def send_naughty_word_log_message(author: User | Member, content: str, guild: Guild):
    escaped_message = content.replace('```', '` ` `')
    full_message = f'Banning `{author.name}` (<@{author.id}>) for message:\n```\n{escaped_message}\n```'
    await send_log_message(guild, full_message)


async def send_rate_limit_log_message(author: User | Member, guild: Guild):
    message = f'Banning `{author.name}` (<@{author.id}>) for posting in {CHANNEL_THRESHOLD} channels within {SECONDS_THRESHOLD} seconds'
    await send_log_message(guild, message)


async def send_log_message(guild: Guild, message: str):
    for channel in guild.text_channels:
        if channel.name in ('actual-log', 'alerta'):
            await channel.send(message)



def main():
    client.run(TOKEN)


if __name__ == '__main__':
    main()
