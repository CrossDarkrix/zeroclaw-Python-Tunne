#!/usr/bin/env python3
#-*- encoding: utf-8 -*-

# Author: CrossDarkRix
# Version: 0.1

import asyncio
import concurrent.futures
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime

# py-cord
import discord
from discord.ext import commands, tasks

TOKEN = ""
TASK = [None]
stopped = [False]

memory_db = os.path.join(os.path.expanduser("~"), ".zeroclaw", "memory.db")
last_tag_file = os.path.join(os.path.expanduser("~"), ".zeroclaw", "last_tag.txt")

class Client(commands.Bot):
    pass

intents = discord.Intents.default()
try:
    intents.message_content = True
except Exception:
    pass
client = Client(command_prefix="!", intents=intents, help_command=None)

def tuple_to_str(_t_list):
    re_list = []
    for tx in _t_list:
        if type(tx) == tuple:
            tuple_to_str(tx)
        else:
            re_list.append(tx)
    return '\n'.join(re_list)

def save_memory(json_data, JSON_TAGS):
    conn = sqlite3.connect(memory_db)
    cur = conn.cursor()
    JSON_TAGS.clear()
    [JSON_TAGS.append(tag) for tag in json_data["tags"]]
    cur.execute("""
        INSERT INTO memories (task, code, result, success, summary, tags, reuse_hint, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
        json_data["task"],
        json_data["code"],
        json_data["result"],
        json_data["success"],
        json_data["summary"],
        json.dumps(json_data["tags"]),
        json_data["reuse_hint"],
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()
    return "タスク: {}\nコード: {}\n結果: {}\n成功: {}\n説明: {}\n再実行時のヒント: {}".format(
        json_data["task"],
            json_data["code"],
            json_data["result"],
            json_data["success"],
            json_data["summary"],
            json_data["reuse_hint"]), JSON_TAGS

def search_memory(JSON_TAGS) -> list:
    conn = sqlite3.connect(memory_db)
    cur = conn.cursor()
    results = []
    try:
        for tag in JSON_TAGS:
            cur.execute("""
            SELECT task, summary, code FROM memories
            WHERE summary LIKE ? OR tags LIKE ?
            ORDER BY id DESC LIMIT 3
            """, (f"%{tag}%", f"%{tag}%"))
            results.extend(cur.fetchall())
        conn.close()
        return results
    except:
        return []

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
        result = subprocess.run(
            ["/opt/homebrew/bin/zeroclaw", "agent", "-m", prompt],
            capture_output=True,
            text=True,
            timeout=600
        )
        output = remove_ansi(result.stdout)
        return clean_output(output) or "⚠️ 出力なし"

    except Exception as e:
        return f"エラー: {e}"

def fix_code_block(text):
    return text.replace('"""', '').strip()

def extract_json(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        data = json.loads(match.group())
        if data:
            data["code"] = fix_code_block(data["code"])
            return data
    return None

class Ai(commands.Cog):
    def __init__(self):
        self.JSON_TAGS = []
        if not os.path.exists(memory_db):
            _conn = sqlite3.connect(memory_db)
            _cur = _conn.cursor()

            _cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT,
                code TEXT,
                result TEXT,
                success BOOLEAN,
                summary TEXT,
                tags TEXT,
                reuse_hint TEXT,
                created_at TEXT
            )
            """)

            _conn.commit()
            _conn.close()

    @discord.slash_command(name="set_learn", description="AIに学習をさせます")
    async def set_learn(self, cx: discord.ApplicationContext, text: str, minutes: int): # 学習機能(自動で学習させたい内容と更新時間(分))
        try:
            await cx.response.send_message(content='AIに自動学習を設定させました。', ephemeral=True)
        except:
            pass
        task = tasks.loop(minutes=minutes)(self.__set_Cron) # タスクとして関数登録
        TASK[0] = task
        task.start(cx, text)

    async def __set_Cron(self, ctx, text):
        if os.path.exists(last_tag_file):
            self.JSON_TAGS = open(last_tag_file, 'r', encoding='utf-8').read().split(',')
        if len(self.JSON_TAGS) != 0:
            mem = search_memory(self.JSON_TAGS)
            if len(mem) != 0:
                prompt = "過去の学習:\n{}\n\nこれを参考に以下のタスクを実行してください\n\n{}".format('\n'.join(tuple_to_str(mem)), text)
            else:
                prompt = "{}".format(text)
        else:
            prompt = "{}".format(text)
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, run_zeroclaw, prompt)
        try:
            json_data = extract_json(output)
            text, json_tags = save_memory(json_data, self.JSON_TAGS)
        except:
            text = "⚠️ 出力なし"
            json_tags = []
        self.JSON_TAGS = json_tags
        with open(last_tag_file, 'w', encoding='utf-8') as _tag:
            _tag.write(','.join(json_tags))
        await ctx.send(content=text)

    @discord.slash_command(name="set_stop", description="学習を停止します。")
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
    await client.change_presence(activity=discord.Game('正常に稼働中 v1.0'))
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
    await message.channel.send("思考中.........")
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
