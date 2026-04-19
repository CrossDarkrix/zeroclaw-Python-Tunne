#!/usr/bin/env python3
#-*- encoding: utf-8 -*-

# Author: CrossDarkRix
# Version: 0.1

import asyncio
import concurrent.futures
import re
import subprocess
import time

# py-cord
import discord
from discord.ext import commands, tasks

TASK = [None]
stopped = [False]
TOKEN = ""

class Client(commands.Bot):
    pass

intents = discord.Intents.default()
try:
    intents.message_content = True
except:
    pass
client = Client(command_prefix="!", intents=intents, help_command=None)


def clean_output(text: str) -> str: # INFO, WRN, DEBUGを消す
    text = remove_ansi(text)
    cleaned = []
    for line in text.splitlines():
        if any(tag in line for tag in ["WARN", "INFO", "DEBUG"]):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)

def remove_ansi(text: str) -> str: # アスキー文字の削除
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def run_zeroclaw(prompt: str) -> str: # ZeroClaw のシングル対話モードで送信
    try:
        result = subprocess.run('zeroclaw agent -m "{}"'.format(prompt),
            capture_output=True,
            text=True,
            timeout=600,
            shell=True,
        )
        output = remove_ansi(result.stdout)
        return clean_output(output) or "⚠️ 出力なし"
    except Exception as e:
        return f"エラー: {e}"


class Ai(commands.Cog):

    @discord.slash_command(name="set_learn", description="AIに学習をさせます")
    async def set_learn(self, cx: discord.ApplicationContext, text: str, minutes: int) -> None: # 学習機能(自動で学習させたい内容と更新時間)
        try:
            await cx.response.send_message(content='AIに学習を設定させました。', ephemeral=True)
        except:
            pass
        task = tasks.loop(minutes=minutes)(self.__set_Cron) # タスクとして関数登録
        TASK[0] = task
        task.start(cx, text)

    async def __set_Cron(self, ctx, text): # タスク化する関数
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, run_zeroclaw, text)
        await ctx.send(content=output)

    @discord.slash_command(name="set_stop", description="学習を停止します")
    async def set_stop(self, cx: discord.ApplicationContext) -> None: # 学習を停止するコマンド
        try:
            TASK[0].stop()
        except:
            pass
        try:
            TASK[0].cancel()
        except:
            pass
        try:
            await cx.delete()
        except:
            pass


@client.event
async def on_ready():
    await client.change_presence(activity=discord.Game('BOTが正常に起動ました'))
    print(f"ログイン: {client.user}")


@client.event
async def on_message(message): # メッセージから指示の取得
    if message.author.bot:
        return
    is_reply = message.reference is not None
    is_mention = client.user in message.mentions
    if not (is_reply or is_mention):
        return
    prompt = message.content
    await message.channel.send("思考中......")
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, run_zeroclaw, prompt)
    await message.channel.send(response)
    await client.process_commands(message)

def TimeCount(): # 稼働時間表示
    Uptimeloop = [0]

    def TimeCounter():
        Year = 0
        Week = 0
        Day = 0
        Hour = 0
        Minute = 0
        Sec = 0
        for i in Uptimeloop:
            if stopped[0]:
                break
            if Sec == 59:
                Sec = 0
                Minute += 1
            else:
                Sec += 1
            if Minute == 59:
                Minute = 0
                Hour += 1
            if Hour == 24:
                Hour = 0
                Day += 1
            if Day == 7:
                Day = 0
                Week += 1
            if Week == 13:
                Week = 0
                Year += 1
            if Year <= 9:
                SYear = '0{}'.format(Year)
            else:
                SYear = '{}'.format(Year)
            if Week <= 9:
                SWeek = '0{}'.format(Week)
            else:
                SWeek = '{}'.format(Week)
            if Day <= 9:
                SDay = '0{}'.format(Day)
            else:
                SDay = '{}'.format(Day)
            if Hour <= 9:
                SHour = '0{}'.format(Hour)
            else:
                SHour = '{}'.format(Hour)
            if Minute <= 9:
                SMinute = '0{}'.format(Minute)
            else:
                SMinute = '{}'.format(Minute)
            if Sec <= 9:
                SSec = '0{}'.format(Sec)
            else:
                SSec = '{}'.format(Sec)
            print('稼働時間: {}年, {}週間, {}日, {}:{}:{}'.format(SYear, SWeek, SDay, SHour, SMinute, SSec), end='\r',
                  flush=True)
            time.sleep(1)
            Uptimeloop.append(i + 1)

    concurrent.futures.ThreadPoolExecutor().submit(TimeCounter)

def main():
    TimeCount()
    client.add_cog(Ai())
    client.run(TOKEN)

if __name__ == '__main__':
    main()
