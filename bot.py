#! /usr/bin/env python3
import asyncio
import os
from dataclasses import dataclass

import discord
from discord import Guild, Member, User
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

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
            self.recent_posts.append(ChannelPost(channel_id=channel_id, author_id=author_id, timestamp=now))
            channel_ids = {p.channel_id for p in self.recent_posts if p.author_id == author_id}
            return len(channel_ids) >= CHANNEL_THRESHOLD


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
        reason = f'Posted in {CHANNEL_THRESHOLD} channels within {SECONDS_THRESHOLD} seconds'
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
