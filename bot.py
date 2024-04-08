#! /usr/bin/env python3

import os

import discord
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
    if '@everyone' in message.content:
        print(f'Banning {message.author}')
        await message.author.ban(reason='Tried to use @everyone', delete_message_seconds=120)


def main():
    client.run(TOKEN)


if __name__ == '__main__':
    main()
