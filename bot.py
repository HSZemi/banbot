#! /usr/bin/env python3

import os

import discord
from discord import Guild, Member, User
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


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
            await send_log_message(message.author, message.content, message.guild)
            return

async def send_log_message(author: User | Member, content: str, guild: Guild):
    for channel in guild.text_channels:
        if channel.name in ('actual-log', 'alerta'):
            escaped_message = content.replace('```', '` ` `')
            await channel.send(f'Banning <@{author.id}> for message:\n```\n{escaped_message}\n```')



def main():
    client.run(TOKEN)


if __name__ == '__main__':
    main()
