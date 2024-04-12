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
    for bad_word in ('@everyone', '@here'):
        if bad_word in message.content:
            print(f'Banning {message.author} for {message.content=} in {message.guild=}')
            await message.author.ban(reason=f'Tried to use {bad_word}', delete_message_seconds=120)
            return


def main():
    client.run(TOKEN)


if __name__ == '__main__':
    main()
